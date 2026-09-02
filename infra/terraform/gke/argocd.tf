resource "helm_release" "argocd" {
  name             = "argocd"
  namespace        = "argocd"
  create_namespace = true
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = var.argocd_chart_version
  values           = [file("${path.module}/../../../platform/argocd/argocd-values.yaml")]
  wait             = true
  timeout          = 600

  depends_on = [google_container_node_pool.system]
}

resource "helm_release" "argocd_bootstrap" {
  name      = "argocd-bootstrap"
  namespace = "argocd"
  chart     = "${path.module}/../../../platform/argocd/bootstrap-chart"

  set = [
    {
      name  = "repo.url"
      value = var.git_repo_url
    },
    {
      name  = "repo.revision"
      value = var.git_revision
    },
    {
      name  = "repo.path"
      value = var.argocd_apps_path
    },
  ]

  set_sensitive = [
    {
      name  = "repo.token"
      value = var.git_repo_token
    },
  ]

  depends_on = [helm_release.argocd]
}
