# TAQA Bid Analyzer Demo

AI-driven commercial bid analysis tool for TAQA/ADDC procurement.

## Getting Started

### Backend (FastAPI)

```bash
cd ~/Desktop/Projects/TAQA/bid_analyzer_demo
uv run uvicorn backend.main:app --reload --port 8000
```

- API: http://localhost:8000/api
- Health check: http://localhost:8000/health

### Frontend (Next.js)

```bash
cd ~/Desktop/Projects/TAQA/bid_analyzer_demo/frontend
npm run dev
```

- UI: http://localhost:3000

### Docker

```bash
docker compose up --build
```

- UI: http://localhost

## Azure Deployment

**Prerequisites**: Azure CLI installed and logged in (`az login`)

### 1. Create resource group and container registry

```bash
az group create --name taqa-bid-analyzer-rg --location uaenorth
```
Create the resource group.

```bash
az acr create --resource-group taqa-bid-analyzer-rg --name taqabidanalyzeracr --sku Basic
```
Create the Azure Container Registry.

```bash
az acr update -n taqabidanalyzeracr --admin-enabled true
```
Enable admin credentials so App Service can pull images.

### 2. Build and push the image

```bash
az acr build --registry taqabidanalyzeracr --image bid-analyzer:latest -f Dockerfile .
```
Build the Docker image in Azure (no local push needed).

### 3. Create App Service and deploy

```bash
az appservice plan create --name taqa-bid-plan --resource-group taqa-bid-analyzer-rg --sku B1 --is-linux
```
Create the App Service plan.

```bash
az webapp create --name taqa-bid-analyzer --resource-group taqa-bid-analyzer-rg --plan taqa-bid-plan --deployment-container-image-name taqabidanalyzeracr.azurecr.io/bid-analyzer:latest
```
Create the web app pulling from ACR.

```bash
az webapp config appsettings set --resource-group taqa-bid-analyzer-rg --name taqa-bid-analyzer --settings AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT='https://taqad-sai.cognitiveservices.azure.com/' AZURE_DOCUMENT_INTELLIGENCE_KEY='<your-key>'
```
Set environment variables for Azure Document Intelligence.

### 4. Link ACR credentials to App Service

```bash
ACR_PWD=$(az acr credential show -n taqabidanalyzeracr --query "passwords[0].value" -o tsv)
```
Retrieve ACR password.

```bash
az webapp config appsettings set --resource-group taqa-bid-analyzer-rg --name taqa-bid-analyzer --settings DOCKER_REGISTRY_SERVER_URL='https://taqabidanalyzeracr.azurecr.io' DOCKER_REGISTRY_SERVER_USERNAME='taqabidanalyzeracr' DOCKER_REGISTRY_SERVER_PASSWORD="$ACR_PWD"
```
Set ACR pull credentials so App Service can pull the image.

### 5. Restart and verify

```bash
az webapp restart --name taqa-bid-analyzer --resource-group taqa-bid-analyzer-rg
```
Restart the app to pick up changes.

- App URL: https://taqa-bid-analyzer.azurewebsites.net

## Making Code Changes

### Test locally with Docker

```bash
docker build -f Dockerfile -t bid-analyzer:local .
```
Build the container locally.

```bash
docker run -d -p 8080:80 --env-file .env bid-analyzer:local
```
Run the container on http://localhost:8080.

```bash
docker stop $(docker ps -q --filter "publish=8080")
```
Stop the local container when done testing.

### Deploy updated image to Azure

```bash
az acr build --registry taqabidanalyzeracr --image bid-analyzer:latest -f Dockerfile .
```
Rebuild the image in ACR with your local changes.

```bash
az webapp restart --name taqa-bid-analyzer --resource-group taqa-bid-analyzer-rg
```
Restart the App Service to pull the new image.