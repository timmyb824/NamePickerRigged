#!/bin/bash

IMAGE_NAME="timothybryantjr"
REGISTRY="registry.local.timmybtech.com"
TAG="latest"
PLATFORM="linux/amd64"
ARGOCD_APP_NAME="name-picker-rigged"
ARGOCD_SERVER="argocd.local.timmybtech.com"
DEPLOYMENT_NAME="name-picker-rigged"
NAMESPACE="name-picker-rigged"
FULL_IMAGE_NAME="$REGISTRY/$IMAGE_NAME:$TAG"

msg_info() {
    echo -e "\033[1;34m[INFO]\033[0m $1"
}

msg_ok() {
    echo -e "\033[1;32m[OK]\033[0m $1"
}

msg_warn() {
    echo -e "\033[1;33m[WARN]\033[0m $1"
}

msg_error() {
    echo -e "\033[1;31m[ERROR]\033[0m $1"
}

handle_error() {
    msg_error "$1"
    exit 1
}

if [ "$1" = "skip" ]; then
    msg_info "Skipping pre-deployment checks..."
else
    msg_info "Checking for uncommitted changes..."
    if [[ -n $(git status --porcelain) ]]; then
        handle_error "Uncommitted changes detected. Please commit or stash them before deploying."
    fi

    msg_info "Checking if on main branch..."
    BRANCH=$(git rev-parse --abbrev-ref HEAD)
    if [[ "$BRANCH" != "main" ]]; then
        handle_error "You must be on the main branch to deploy (current: $BRANCH)."
    fi
fi

check_k8s_cluster() {
    msg_info "Checking we are pointing to the prod cluster (k3s-prod)..."
    if ! kubectl config current-context | grep -q "k3s-prod"; then
        handle_error "You must be pointing to the prod cluster (k3s-prod) to deploy."
    fi
}

build_and_push_image() {
    msg_info "Building image for platform $PLATFORM..."
    if ! podman build --platform $PLATFORM -t $IMAGE_NAME . --no-cache; then
        handle_error "Failed to build image."
    fi

    msg_info "Tagging image..."
    if ! podman tag $IMAGE_NAME $FULL_IMAGE_NAME; then
        handle_error "Failed to tag image."
    fi

    msg_info "Pushing image to registry..."
    if ! podman push $FULL_IMAGE_NAME; then
        handle_error "Failed to push image."
    fi
}

refresh_argocd_app() {
    if command -v argocd >/dev/null 2>&1; then
        msg_info "ArgoCD CLI detected, attempting to refresh application..."
        argocd login $ARGOCD_SERVER --grpc-web --username $ARGOCD_USER --password $ARGOCD_USER_PASSWORD
        if argocd app get "$ARGOCD_APP_NAME" --grpc-web >/dev/null 2>&1; then
            argocd app get "$ARGOCD_APP_NAME" --hard-refresh --grpc-web
            msg_ok "ArgoCD application refresh triggered successfully!"
        else
            msg_warn "Warning: ArgoCD application '$ARGOCD_APP_NAME' not found. Please verify the application name and your ArgoCD login status."
            msg_warn "You may need to refresh the application manually via the ArgoCD UI."
        fi
    else
        msg_warn "Note: ArgoCD CLI not found. To update the deployment, please refresh the application in the ArgoCD UI."
    fi
}

restart_argocd_deployment() {
    if command -v kubectl >/dev/null 2>&1; then
        msg_info "Kubectl detected, restarting deployment..."
        kubectl rollout restart deployment/$DEPLOYMENT_NAME -n $NAMESPACE
        msg_ok "Deployment restarted successfully!"
    else
        msg_warn "Note: Kubectl not found. To restart the deployment, please run 'kubectl rollout restart deployment/$DEPLOYMENT_NAME' manually."
    fi
}

check_k8s_cluster
build_and_push_image
refresh_argocd_app
restart_argocd_deployment

msg_ok "Deployment script completed successfully!"
