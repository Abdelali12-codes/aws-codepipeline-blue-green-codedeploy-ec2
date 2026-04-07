import aws_cdk as cdk
from stack import BlueGreenEC2CodeDeployStack

app = cdk.App()
infra = BlueGreenEC2CodeDeployStack(app, "BlueGreenEC2CodeDeployStack",
                                    env=cdk.Environment(region="us-east-2")
                                    )
app.synth()
