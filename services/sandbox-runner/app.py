from fastapi import FastAPI
from pydantic import BaseModel
from quantum_agent.coding.sandbox import SubprocessSandbox
from quantum_agent.coding.models import CodeArtifact
from quantum_agent.science.models import SandboxLimits

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_sandbox = SubprocessSandbox()

class ExecuteRequest(BaseModel):
    code: str
    limits: SandboxLimits

@app.post("/execute")
async def execute(request: ExecuteRequest):
    artifact = CodeArtifact(purpose="isolated execution", code=request.code)
    result = await _sandbox.execute_program(artifact, request.limits)
    return result.model_dump(mode="json")
