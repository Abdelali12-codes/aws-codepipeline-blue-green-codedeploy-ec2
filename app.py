import aws_cdk as cdk
from stack import BlueGreenEC2CodeDeployStack

app = cdk.App()
infra = BlueGreenEC2CodeDeployStack(app, "BlueGreenEC2CodeDeployStack")
app.synth()
