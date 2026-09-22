# New Renglo environment (operator)

This is the from-scratch path. When you finish, AWS has a running platform (login, mail, storage, identity) and you have a folder of config files to give developers.

You do not need to know how the platform is built. You run the commands below, in order. If you lose your place, run `renglo status` — it prints the next command.

`arbitium` is the same program as `renglo`. Use either name.

---

## What you will have at the end

- Two AWS stacks for this environment: **A** (core platform) and **B** (hub-side extension infrastructure)
- A verified sender address so the system can send mail
- One admin user in the login pool
- A **handover folder** at `bootstrap/output/<env-name>/local-dev/`

The hosted API is still a placeholder. Developers run the real API and console on their laptops using the handover folder. That is expected.

---



## Before you start



### On this laptop


| Need                      | Why                                                                                                        |
| ------------------------- | ---------------------------------------------------------------------------------------------------------- |
| **macOS or Linux**        | The commands below are bash.                                                                               |
| **Git**                   | Clone the platform repos.                                                                                  |
| **Python 3.12**           | The installer and the CLI require it. Check: `python3.12 --version`. On macOS: `brew install python@3.12`. |
| **Node.js + AWS CDK CLI** | Deploys the stacks. Install once: `npm install -g aws-cdk`. Check: `cdk --version`.                        |
| **AWS CLI v2**            | Named profiles and `sts`. Check: `aws --version`.                                                          |




### AWS


| Need                                                                                                                                                                                                                                                                                        | Why |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --- |
| **An AWS account** that this environment will live in. Do not reuse an account that already has a tenant with the same `--env-name`.                                                                                                                                                        |     |
| **A named AWS CLI profile** with credentials for that account (access keys, SSO, or any method `aws configure` / `aws sso login` supports). This is what people mean by “an AWS token” here. Check: `aws configure list-profiles` and `aws sts get-caller-identity --profile YOUR_PROFILE`. |     |
| **Permission to create** CloudFormation stacks, IAM roles, Cognito, SES, S3, DynamoDB, Lambda, SSM, and (first time in this account/region) a CDK bootstrap stack. An account admin can grant this.                                                                                         |     |
| **A region.** `us-east-1` is the usual choice. Pass `--region` if you use another.                                                                                                                                                                                                          |     |


The first deploy in an account/region also bootstraps CDK. `renglo system install apply` does that for you.

### GitHub


| Need                                                                                                                                                                                                                                                                            | Why |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --- |
| **Access to clone** `renglo/bootstrap`, `renglo/launcher`, `renglo/bom-helper`, and `renglo/renglo-cli` (private org repos). Use SSH or HTTPS with a GitHub credential.                                                                                                         |     |
| **A** `*-bom` **repository** for this tenant — for example `YourOrg/acme-bom`. It holds the pin list CI will use later. Create an empty repo, or copy `example-bom`. You need the `ORG/REPO` name for `--github-repo` even if you do not clone the BOM into this workspace yet. |     |


You do **not** clone product apps (`renglo-api`, `console`) or any extension for this path.

### Names you must choose now

Write these down. You will type them once.


| Choice                | Rules                                                                                                                                                      |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Env name**          | Short, unique in the account. Letters and digits. Becomes the stack prefix (`acme0922` → `acme0922-stack-a`). Do not reuse a name that already has stacks. |
| **AWS profile**       | The named profile from above.                                                                                                                              |
| **AWS region**        | Usually `us-east-1`.                                                                                                                                       |
| **BOM repo**          | `YourOrg/your-bom` (no `.git`).                                                                                                                            |
| **Sender address**    | Who the system writes *from* (`noreply@your-domain.com`, or a single inbox you control).                                                                   |
| **Sender type**       | `domain` if you own the DNS for that domain; `email` if you will click a confirmation link in one inbox.                                                   |
| **Route 53 zone id**  | Only if the domain’s DNS already lives in this AWS account. Otherwise omit it (you will add DNS records by hand).                                          |
| **First admin email** | A real inbox. Cognito will send a temporary password there.                                                                                                |


New AWS accounts start SES in **sandbox**: the system can send *to* only addresses you allow. Allow every inbox you will use for tests. Production-access (send to anyone) is an AWS request; this CLI does not file it.

---



## 1. Create a blank workspace and clone

Do this in an empty folder. Do **not** put it inside an existing product tree.

```bash
mkdir acme && cd acme

git clone git@github.com:renglo/bootstrap.git bootstrap
git clone git@github.com:renglo/launcher.git launcher
git clone git@github.com:renglo/bom-helper.git bom-helper
git clone git@github.com:renglo/renglo-cli.git renglo-cli
```

HTTPS if you do not use SSH:

```bash
git clone https://github.com/renglo/bootstrap.git bootstrap
git clone https://github.com/renglo/launcher.git launcher
git clone https://github.com/renglo/bom-helper.git bom-helper
git clone https://github.com/renglo/renglo-cli.git renglo-cli
```

You should see four directories: `bootstrap`, `launcher`, `bom-helper`, `renglo-cli`.

If `renglo-cli` is not on GitHub yet, copy it from a machine that already has `ops/renglo-cli`.

Optional: clone the BOM next to them (`git clone git@github.com:YourOrg/your-bom.git your-bom`). The first install does not require that checkout.

---



## 2. Install the tools on this machine

Still in the workspace root (`~/renglo-envs/acme` in the example).

```bash
# Platform Python env (do not copy this venv from another computer)
bash bootstrap/setup-venvs.sh

# Operator CLI
cd renglo-cli
bash setup_venv.sh
source renglo-venv/bin/activate
cd ..
```

Keep that venv active for the rest of this document (`which renglo` should print a path under `renglo-cli/renglo-venv`).

```bash
renglo doctor --profile YOUR_PROFILE
```

Every check should be `ok`. If AWS `sts` fails, fix the profile before you continue.

---



## 3. Name the environment

Replace the placeholders.

```bash
renglo system init \
  --env-name acme0922 \
  --github-repo YourOrg/your-bom \
  --email-from noreply@your-domain.com \
  --email-identity-type domain \
  --enable-staging
```

Add `--email-hosted-zone-id Z…` only when Route 53 in this account owns the domain.

Use `--email-identity-type email` and a mailbox you can open if you do not have a domain yet.

Use `--compute-type lambda_only` only if you need to say it explicitly; that is already the default. Do not pick `fargate` or `ec2` for a first bring-up unless you already know you need container handlers.

This writes identity only. Nothing is deployed yet.

---



## 4. Build the platform in AWS

```bash
renglo system install start --profile YOUR_PROFILE
renglo system install plan          # optional: see remaining phases
renglo system install apply
```

`apply` synthesizes the apps, bootstraps CDK in the account/region if needed, deploys stack **A** then stack **B**, and registers URLs and the sender in AWS.

It **stops before** mail verification and the first admin. That is intentional.

If it fails halfway, fix the error and run `renglo system install apply` again. Finished phases are skipped. `renglo status` shows where you are.

`--dry-run` on `apply` prints what would run.

---



## 5. Prove the sender, create the first admin

```bash
renglo email sender-status
renglo email verify-sender
```

- **domain:** wait until the domain shows `Success`. If DNS is not automatic, add the records AWS shows and re-run `verify-sender`.
- **email:** open the mailbox, click the AWS confirmation link, then re-run `verify-sender`.

```bash
renglo admin create you@example.com
```

Cognito emails a temporary password. Open the **setup** URL the command prints (or the local one later: `http://127.0.0.1:5174/invite?setup=admin&email=you@example.com`) and set a real password.

```bash
renglo admin show you@example.com
```

---



## 6. Allow test inboxes (SES sandbox)

Skip this once the account has SES production access (`renglo email sender-status` says you are not in sandbox).

```bash
renglo email allow you@example.com
renglo email allow teammate@example.com
renglo email allow-status
```

Each person must click the SES confirmation mail. `Pending` means they have not clicked yet. `Success` means the system may send to that address.

---



## 7. Handover folder for developers

```bash
renglo state local-config
```

That writes:

```text
bootstrap/output/<env-name>/local-dev/
  env_config.py         →  copy to  dev/renglo-api/env_config.py
  run.sh                →  copy to  dev/renglo-api/run.sh
  .env.development      →  copy to  console/.env.development
  README.md             →  keep with the bundle (do not copy into the apps)
```

Zip or share **that folder**. Developers follow `local-dev/README.md`. They still need an AWS profile that can reach this same account.

If you later change stacks or the sender, run `renglo state local-config` again and resend the folder.

Check what was registered:

```bash
renglo state show
renglo stack status
```

---



## Command checklist

```text
# once per machine, in the workspace
bash bootstrap/setup-venvs.sh
cd renglo-cli && bash setup_venv.sh && source renglo-venv/bin/activate && cd ..
renglo doctor --profile YOUR_PROFILE

# once per environment
renglo system init --env-name NAME --github-repo ORG/BOM \
  --email-from ADDR --email-identity-type domain --enable-staging
renglo system install start --profile YOUR_PROFILE
renglo system install apply
renglo email verify-sender
renglo admin create ADMIN@EXAMPLE.COM
renglo email allow ADMIN@EXAMPLE.COM
renglo state local-config
```

Handover: `bootstrap/output/NAME/local-dev/`

---



## If something goes wrong


| Symptom                                           | What to do                                                                                                                      |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `workspace root not found`                        | `cd` to the folder that contains `bootstrap/` and `launcher/`, or pass `--workspace PATH`.                                      |
| `python3.12` / `cdk` / `aws_cdk` fail in `doctor` | Install those tools; re-run `bash bootstrap/setup-venvs.sh`. Do not copy `bootstrap/venv` from another machine.                 |
| `sts` fails                                       | `aws sts get-caller-identity --profile YOUR_PROFILE`. Re-login (SSO) if needed.                                                 |
| Stack already exists                              | You reused `--env-name`. Pick a new name or destroy the old stacks first.                                                       |
| Mail not sending                                  | `renglo email sender-status` and `renglo email allow-status`. Sandbox requires `Success` on both the sender and each recipient. |
| Need to start over                                | `renglo system destroy --yes` (B then A). Peer stacks, if any, are destroyed separately.                                        |


Full command list: [README.md](README.md).