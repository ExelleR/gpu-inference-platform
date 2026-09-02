{{- define "vllm.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "vllm.labels" -}}
app.kubernetes.io/name: {{ include "vllm.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: vllm
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "vllm.selectorLabels" -}}
app.kubernetes.io/name: {{ include "vllm.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
