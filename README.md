# 19 - Blue/Green: CodeDeploy on EC2

## Technique
CodeDeploy provisions a brand new set of EC2 instances (green), deploys the
new revision to them, shifts ALB traffic from blue → green, then terminates
the blue instances after a configurable wait time.

## Hook execution order
```
BLUE instances:
  BeforeBlockTraffic → [BlockTraffic] → AfterBlockTraffic

GREEN instances (new):
  BeforeInstall → [Install] → AfterInstall → ApplicationStart → ValidateService
  BeforeAllowTraffic → [AllowTraffic] → AfterAllowTraffic

BLUE instances terminated after wait time
```

## Deploy
```bash
pip install -r requirements.txt
cdk deploy
```

## Trigger deployment
```bash
aws deploy create-deployment \
  --application-name bg-ec2-app \
  --deployment-group-name bg-ec2-dg \
  --s3-location bucket=<BUCKET>,key=<KEY>,bundleType=zip
```
