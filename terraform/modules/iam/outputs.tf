output "eks_cluster_role_arn" {
  value = aws_iam_role.eks_cluster.arn
}

output "eks_node_role_arn" {
  value = aws_iam_role.eks_node.arn
}

output "ebs_csi_role_arn" {
  value = aws_iam_role.ebs_csi.arn
}

output "lb_controller_role_arn" {
  value = aws_iam_role.lb_controller.arn
}

output "app_backend_role_arn" {
  value = aws_iam_role.app_backend.arn
}

output "oidc_provider_arn" {
  value = local.oidc_provider_arn
}
