{{/*
Expand the name of the chart (same pattern as `helm create`).
*/}}
{{- define "insomnia.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Deployment/Service selector: single label only. Adding app.kubernetes.io/instance to the
selector breaks upgrades when the live Deployment was created with name-only matchLabels
(spec.selector is immutable).
*/}}
{{- define "insomnia.matchLabels" -}}
app.kubernetes.io/name: {{ include "insomnia.name" . }}
{{- end }}

{{/*
Pod template labels (selector is a subset; instance is metadata only).
*/}}
{{- define "insomnia.podLabels" -}}
app.kubernetes.io/name: {{ include "insomnia.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
