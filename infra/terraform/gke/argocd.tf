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
  # The root Application reconciles asynchronously; do not block apply on Argo CD syncing it.
  wait    = false
  timeout = 900

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
    {
      name  = "serving.enabled"
      value = tostring(var.serving_enabled)
    },
    {
      name  = "monitoring.enabled"
      value = "true"
    },
    {
      name  = "observability.enabled"
      value = tostring(var.observability_enabled)
    },
    {
      name  = "observability.projectId"
      value = var.project_id
    },
    {
      name  = "observability.gsaEmail"
      value = try(google_service_account.gmp_frontend[0].email, "")
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
