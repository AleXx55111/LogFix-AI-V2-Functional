# Cloud access & API credentials — LogFix AI V2.1

The cloud connectors make **bounded read-only queries** (last 30 minutes, up to 100 records per cloud) through official SDKs. They **do not** perform remediation or modify infrastructure. Cloud logs must already be available in the relevant cloud logging product.

## Private instance only

Never unlock real logs in the public demonstration. Keep `PUBLIC_DEMO_ONLY=true` for the shared link; create a separate instance with `PUBLIC_DEMO_ONLY=false`, `APP_ADMIN_KEY=<long-random-key>` **and** strong access control such as SSO/IAP/VPN before using sensitive real data. An admin key alone is not sufficient for production exposure.

In Cloud Connections:

1. Unlock using your `APP_ADMIN_KEY`.
2. Fill **resource selectors** and click **Save selectors**.
3. Fill **write-only credential fields** and click **Save credentials**. Values live in backend RAM only until a restart. Existing values are not returned to the browser; an empty field leaves them unchanged.
4. Press **Test selected clouds** to make bounded real API queries. Errors are deliberately sanitized, so check private service logs and IAM settings for more detail.
5. Run a single cloud at a time under **Run & Schedule**. An authorized connection with 0 events can still be healthy; generate a known test event to verify log ingestion.

For always-on identities, set secrets in the hosting environment or use workload identity (preferred). The UI-entered keys do not survive instance restarts.

### Azure Log Analytics

| Variable / UI field | Meaning |
|---|---|
| `AZURE_WORKSPACE_ID` | Log Analytics Workspace ID (GUID), **not** the subscription ID |
| `AZURE_LOG_TABLE` | `AppTraces`, `AzureDiagnostics`, `Syslog`, `Event`, `ContainerLogV2` |
| `AZURE_TENANT_ID` | Entra tenant ID |
| `AZURE_CLIENT_ID` | Service principal application/client ID |
| `AZURE_CLIENT_SECRET` | Service principal secret |

Minimum commonly used role: **Log Analytics Data Reader** on the workspace. When no explicit triple is provided, the connector uses Azure SDK `DefaultAzureCredential`, excluding interactive browser authentication. Azure environment variables are supported by that chain; `az login` is useful locally.

### AWS CloudWatch Logs

| Variable / UI field | Meaning |
|---|---|
| `AWS_REGION` | Log group region (example `ap-south-1`) |
| `AWS_LOG_GROUP` | Full CloudWatch Logs group name |
| `AWS_ACCESS_KEY_ID` | IAM access key (or assume an SDK role instead) |
| `AWS_SECRET_ACCESS_KEY` | Matching IAM secret access key |
| `AWS_SESSION_TOKEN` | Optional STS temporary token |

Use IAM `logs:FilterLogEvents` on the chosen log-group ARN, with organization policies checked. boto3 credential chain is used when keys are not explicitly provided.

### GCP Cloud Logging

| Variable / UI field | Meaning |
|---|---|
| `GCP_PROJECT_ID` | Project owning the log entries |
| `GCP_SERVICE_ACCOUNT_JSON` | JSON key for an identity with read access; write-only in admin UI |
| `GOOGLE_APPLICATION_CREDENTIALS` | Alternative private file path for ADC, or workload identity |

Assign `roles/logging.viewer` on the project. Restricted/private logs may need extra permissions. Prefer workload identity rather than a long-lived JSON key on a third-party hosting platform.

## AI model

Navigate to **AI Settings** (private only). Enter `OPENAI_API_KEY`, choose `OPENAI_MODEL`, enable LLM, save. Then either (a) choose **Use AI for private questions**, or (b) explicitly enable **Automatically generate AI RCA after each run** (including scheduled runs) to create a draft attached to stored RCA. This can incur API charges. AI evidence is redacted and bounded, but redaction is heuristic and cannot guarantee privacy.

## Security caveats

- No public service should be able to access live clouds or set secrets; demo lock enforces this.
- Private admin mode is MVP-quality access protection, not user authentication, MFA, or audited multi-tenancy.
- Do not store root/owner cloud credentials or enable write policies.
- The app sanitizes logs before storing them, but source log messages can contain formats missed by regex patterns. Review before handling confidential material.
- Cloud connectivity, accounts, regions, IAM policies, billing, and data ingestion have to be validated with **your own** identities, not just mocked tests.
