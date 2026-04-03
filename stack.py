import aws_cdk as cdk
from aws_cdk import (
    aws_codedeploy as codedeploy,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_elasticloadbalancingv2 as elbv2,
    aws_autoscaling as autoscaling,
    aws_codepipeline as codepipeline,
    aws_codebuild as codebuild,
    aws_s3 as s3,
)
from constructs import Construct


class BlueGreenEC2CodeDeployStack(cdk.Stack):
    """
    Blue/Green deployment on EC2 using CodeDeploy.

    How it works:
    - CodeDeploy launches a NEW set of EC2 instances (green) from the same
      launch template as the original (blue) instances
    - Deploys the new revision to the green instances
    - Shifts ALB traffic from blue target group → green target group
    - Terminates blue instances after the wait time expires

    Key difference from in-place:
    - IN_PLACE  → deploy to SAME instances (brief downtime per instance)
    - BLUE_GREEN → deploy to NEW instances, then swap traffic (zero downtime)

    CodeDeploy blue/green for EC2 REQUIRES an ALB — it needs two target groups
    to shift traffic between blue and green instance sets.
    """

    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        vpc = ec2.Vpc(self, "Vpc", max_azs=2, nat_gateways=1)

        instance_role = iam.Role(
            self, "InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
            ],
        )

        # Ubuntu user data — installs CodeDeploy agent using the official
        # Ubuntu install script from S3. ruby is required by the agent.
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "export DEBIAN_FRONTEND=noninteractive",
            "apt-get update -qq",
            "apt-get install -y -qq ruby wget python3 python3-pip python3-venv iproute2 curl",
            # CodeDeploy agent install for Ubuntu
            "wget -q https://aws-codedeploy-us-east-1.s3.amazonaws.com/latest/install",
            "chmod +x ./install",
            "./install auto",
            "systemctl enable codedeploy-agent",
            "systemctl start codedeploy-agent",
        )

        sg = ec2.SecurityGroup(self, "Sg", vpc=vpc)
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8080))

        # Blue ASG — original instances (CodeDeploy will clone this for green)
        blue_asg = autoscaling.AutoScalingGroup(
            self, "BlueAsg",
            vpc=vpc,
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
            machine_image=ec2.MachineImage.from_ssm_parameter(
                # Latest Ubuntu 22.04 LTS AMI via SSM parameter
                "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id"
            ),
            role=instance_role,
            user_data=user_data,
            security_group=sg,
            min_capacity=2,
            max_capacity=4,
            desired_capacity=2,
        )

        alb = elbv2.ApplicationLoadBalancer(self, "Alb", vpc=vpc, internet_facing=True)

        # Blue target group — active production traffic
        blue_tg = elbv2.ApplicationTargetGroup(
            self, "BlueTg",
            vpc=vpc,
            port=8080,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.INSTANCE,
            health_check=elbv2.HealthCheck(path="/health"),
            deregistration_delay=cdk.Duration.seconds(30),
        )

        # Green target group — CodeDeploy registers new instances here
        green_tg = elbv2.ApplicationTargetGroup(
            self, "GreenTg",
            vpc=vpc,
            port=8080,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.INSTANCE,
            health_check=elbv2.HealthCheck(path="/health"),
            deregistration_delay=cdk.Duration.seconds(30),
        )

        listener = alb.add_listener("Listener", port=80, default_target_groups=[blue_tg])
        blue_asg.attach_to_application_target_group(blue_tg)

        application = codedeploy.ServerApplication(
            self, "App", application_name="bg-ec2-app"
        )

        # CodeDeploy service role
        codedeploy_role = iam.Role(
            self, "CodeDeployRole",
            assumed_by=iam.ServicePrincipal("codedeploy.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AWSCodeDeployRole"
                ),
            ],
        )

        # L1 CfnDeploymentGroup — required because the L2 ServerDeploymentGroup
        # does NOT expose blueGreenDeploymentConfiguration or deploymentStyle.
        #
        # deploymentStyle:
        #   deploymentType: BLUE_GREEN   → provision new instances (green)
        #   deploymentOption: WITH_TRAFFIC_CONTROL → shift ALB listener
        #
        # blueGreenDeploymentConfiguration:
        #   deploymentReadyOption → how long to wait before shifting traffic
        #     CONTINUE_DEPLOYMENT  → shift immediately when green is healthy
        #     STOP_DEPLOYMENT      → wait for manual approval before shifting
        #
        #   greenFleetProvisioningOption:
        #     COPY_AUTO_SCALING_GROUP → CodeDeploy clones the blue ASG to
        #                               create the green fleet automatically
        #
        #   terminateBlueInstancesOnDeploymentSuccess:
        #     action: TERMINATE        → terminate blue after traffic shifts
        #     terminationWaitTimeInMinutes → wait N min before terminating
        #                                    (gives time to monitor green)
        #
        # loadBalancerInfo:
        #   targetGroupPairInfoList → pairs blue TG + green TG under the
        #                             same listener. CodeDeploy updates the
        #                             listener default action to point to
        #                             green TG when traffic shifts.
        codedeploy.CfnDeploymentGroup(
            self, "DeploymentGroup",
            application_name=application.application_name,
            deployment_group_name="bg-ec2-dg",
            service_role_arn=codedeploy_role.role_arn,
            deployment_config_name="CodeDeployDefault.AllAtOnce",
            auto_scaling_groups=[blue_asg.auto_scaling_group_name],
            # ── Deployment style: blue/green with ALB traffic control ───
            deployment_style=codedeploy.CfnDeploymentGroup.DeploymentStyleProperty(
                deployment_type="BLUE_GREEN",
                deployment_option="WITH_TRAFFIC_CONTROL",
            ),
            # ── Blue/green specific configuration ───────────────────────
            blue_green_deployment_configuration=codedeploy.CfnDeploymentGroup.BlueGreenDeploymentConfigurationProperty(
                # How CodeDeploy handles traffic shift readiness:
                # CONTINUE_DEPLOYMENT → shift traffic immediately once green
                #                       instances pass health checks
                deployment_ready_option=codedeploy.CfnDeploymentGroup.DeploymentReadyOptionProperty(
                    action_on_timeout="CONTINUE_DEPLOYMENT",
                    # wait_time_in_minutes=0  (only used with STOP_DEPLOYMENT)
                ),
                # Clone the blue ASG to provision the green fleet.
                # CodeDeploy copies the launch template, capacity, and
                # subnet config from the original ASG.
                green_fleet_provisioning_option=codedeploy.CfnDeploymentGroup.GreenFleetProvisioningOptionProperty(
                    action="COPY_AUTO_SCALING_GROUP",
                ),
                # Terminate blue instances after traffic fully shifts to green.
                # terminationWaitTimeInMinutes gives you a window to monitor
                # green before blue is gone — set to 0 for immediate cleanup.
                terminate_blue_instances_on_deployment_success=codedeploy.CfnDeploymentGroup.BlueInstanceTerminationOptionProperty(
                    action="TERMINATE",
                    termination_wait_time_in_minutes=5,
                ),
            ),
            # ── ALB traffic shift configuration ─────────────────────────
            # targetGroupPairInfoList tells CodeDeploy:
            #   - which listener to update
            #   - which TG is blue (current) and which is green (new)
            # When traffic shifts:
            #   listener default action → green TG  (green is now live)
            #   blue TG                → drained and deregistered
            load_balancer_info=codedeploy.CfnDeploymentGroup.LoadBalancerInfoProperty(
                target_group_pair_info_list=[
                    codedeploy.CfnDeploymentGroup.TargetGroupPairInfoProperty(
                        target_groups=[
                            codedeploy.CfnDeploymentGroup.TargetGroupInfoProperty(
                                name=blue_tg.target_group_name,  # blue = current
                            ),
                            codedeploy.CfnDeploymentGroup.TargetGroupInfoProperty(
                                name=green_tg.target_group_name,  # green = new
                            ),
                        ],
                        prod_traffic_route=codedeploy.CfnDeploymentGroup.TrafficRouteProperty(
                            listener_arns=[listener.listener_arn],
                        ),
                    )
                ]
            ),
            auto_rollback_configuration=codedeploy.CfnDeploymentGroup.AutoRollbackConfigurationProperty(
                enabled=True,
                events=["DEPLOYMENT_FAILURE"],
            ),
        )

        cdk.CfnOutput(self, "AlbDns", value=alb.load_balancer_dns_name)
        cdk.CfnOutput(self, "BlueTgArn", value=blue_tg.target_group_arn)
        cdk.CfnOutput(self, "GreenTgArn", value=green_tg.target_group_arn)
        cdk.CfnOutput(self, "ListenerArn", value=listener.listener_arn)

        # ── Artifact bucket ─────────────────────────────────────────────
        artifact_bucket = s3.Bucket(
            self, "ArtifactBucket",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=True,
        )

        # ── CodeBuild — packages app/ + appspec.yml + scripts/ ──────────
        build_role = iam.Role(
            self, "BuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
        )
        artifact_bucket.grant_read_write(build_role)
        build_role.add_to_policy(iam.PolicyStatement(
            actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
            resources=["*"],
        ))

        build_project = codebuild.CfnProject(
            self, "BuildProject",
            name="bg-ec2-build",
            service_role=build_role.role_arn,
            artifacts=codebuild.CfnProject.ArtifactsProperty(type="CODEPIPELINE"),
            environment=codebuild.CfnProject.EnvironmentProperty(
                type="LINUX_CONTAINER",
                compute_type="BUILD_GENERAL1_SMALL",
                image="aws/codebuild/standard:7.0",
            ),
            source=codebuild.CfnProject.SourceProperty(
                type="CODEPIPELINE",
                build_spec="\n".join([
                    "version: 0.2",
                    "phases:",
                    "  build:",
                    "    commands:",
                    "      - echo Build started",
                    "artifacts:",
                    "  files:",
                    "    - appspec.yml",
                    "    - scripts/**/*",
                    "    - app/**/*",
                ]),
            ),
        )

        # ── Pipeline role ───────────────────────────────────────────────
        pipeline_role = iam.Role(
            self, "PipelineRole",
            assumed_by=iam.ServicePrincipal("codepipeline.amazonaws.com"),
        )
        artifact_bucket.grant_read_write(pipeline_role)
        pipeline_role.add_to_policy(iam.PolicyStatement(
            actions=["codebuild:BatchGetBuilds", "codebuild:StartBuild"],
            resources=["*"],
        ))
        pipeline_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "codedeploy:CreateDeployment", "codedeploy:GetDeployment",
                "codedeploy:GetDeploymentConfig", "codedeploy:GetApplicationRevision",
                "codedeploy:RegisterApplicationRevision",
            ],
            resources=["*"],
        ))

        # ── CfnPipeline ─────────────────────────────────────────────────
        # Source: GitHub (ThirdParty provider, OAuth token from Secrets Manager)
        # Build:  CodeBuild packages the deployment artifact
        # Deploy: CodeDeploy blue/green — provisions new green EC2 instances,
        #         deploys revision, shifts ALB traffic, terminates blue
        codepipeline.CfnPipeline(
            self, "Pipeline",
            name="bg-ec2-pipeline",
            role_arn=pipeline_role.role_arn,
            artifact_store=codepipeline.CfnPipeline.ArtifactStoreProperty(
                type="S3",
                location=artifact_bucket.bucket_name,
            ),
            restart_execution_on_update=False,
            stages=[
                # ── Stage 1: Source (GitHub) ─────────────────────────────
                # Triggers on push to main via webhook.
                # OAuthToken stored in Secrets Manager — never hardcoded.
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    name="Source",
                    actions=[
                        codepipeline.CfnPipeline.ActionDeclarationProperty(
                            name="GitHub_Source",
                            action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                                category="Source",
                                owner="ThirdParty",
                                provider="GitHub",
                                version="1",
                            ),
                            output_artifacts=[
                                codepipeline.CfnPipeline.OutputArtifactProperty(name="SourceOutput")
                            ],
                            configuration={
                                "Owner": "Abdelali12-codes",
                                "Repo": "aws-codedeploy-sample",
                                "Branch": "master",
                                "OAuthToken": cdk.SecretValue.secrets_manager("github-access-token").unsafe_unwrap(),
                                "PollForSourceChanges": False,
                            },
                            run_order=1,
                        )
                    ],
                ),
                # ── Stage 2: Build ───────────────────────────────────────
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    name="Build",
                    actions=[
                        codepipeline.CfnPipeline.ActionDeclarationProperty(
                            name="Build",
                            action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                                category="Build",
                                owner="AWS",
                                provider="CodeBuild",
                                version="1",
                            ),
                            input_artifacts=[
                                codepipeline.CfnPipeline.InputArtifactProperty(name="SourceOutput")
                            ],
                            output_artifacts=[
                                codepipeline.CfnPipeline.OutputArtifactProperty(name="BuildOutput")
                            ],
                            configuration={"ProjectName": build_project.name},
                            run_order=1,
                        )
                    ],
                ),
                # ── Stage 3: Deploy (CodeDeploy blue/green EC2) ──────────
                # CodeDeploy reads appspec.yml from BuildOutput and:
                #   1. Provisions new green EC2 instances
                #   2. Runs hooks: BeforeInstall → Install → AfterInstall
                #      → ApplicationStart → ValidateService
                #   3. Runs ELB hooks: BeforeAllowTraffic → AllowTraffic
                #      → AfterAllowTraffic
                #   4. Shifts ALB traffic blue → green
                #   5. Terminates blue instances after wait time
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    name="Deploy",
                    actions=[
                        codepipeline.CfnPipeline.ActionDeclarationProperty(
                            name="Deploy",
                            action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                                category="Deploy",
                                owner="AWS",
                                provider="CodeDeploy",
                                version="1",
                            ),
                            input_artifacts=[
                                codepipeline.CfnPipeline.InputArtifactProperty(name="BuildOutput")
                            ],
                            configuration={
                                "ApplicationName": application.application_name,
                                "DeploymentGroupName": "bg-ec2-dg",
                            },
                            run_order=1,
                        )
                    ],
                ),
            ],
        )
