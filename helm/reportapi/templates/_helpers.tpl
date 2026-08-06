{{- define "reportapi.fullname" -}}
{{- .Release.Name }}-reportapi
{{- end -}}

{{- define "reportapi.labels" -}}
app.kubernetes.io/name: reportapi
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
