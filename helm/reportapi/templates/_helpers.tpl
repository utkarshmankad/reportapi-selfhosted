{{- define "reportapi.fullname" -}}
{{- .Release.Name }}-reportapi
{{- end -}}

{{- define "reportapi.labels" -}}
app.kubernetes.io/name: reportapi
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "reportapi.runtimeConfigClaimName" -}}
{{- default (printf "%s-runtime-config" (include "reportapi.fullname" .)) .Values.runtimeConfig.persistence.existingClaim -}}
{{- end -}}

{{- define "reportapi.databaseUrl" -}}
{{- if .Values.postgresql.enabled -}}
postgresql+asyncpg://{{ .Values.postgresql.auth.username | urlquery }}:{{ .Values.postgresql.auth.password | urlquery }}@{{ .Release.Name }}-postgresql:5432/{{ .Values.postgresql.auth.database | urlquery }}
{{- else -}}
{{- required "externalDatabase.url is required when postgresql.enabled=false" .Values.externalDatabase.url -}}
{{- end -}}
{{- end -}}

{{- define "reportapi.redisUrl" -}}
{{- if .Values.redis.enabled -}}
redis://{{ .Release.Name }}-redis-master:6379/0
{{- else -}}
{{- required "externalRedis.url is required when redis.enabled=false" .Values.externalRedis.url -}}
{{- end -}}
{{- end -}}
