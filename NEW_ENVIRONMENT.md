# New Renglo environment (operator)

This is the from-scratch path. When you finish, AWS has a running platform (login, mail, storage, identity), worker **peer** stacks, and a **first product version** taken from a BOM somebody already cut — not from a laptop checkout of the apps.

You do not need to know how the platform is built. You run the commands below, in order. If you lose your place, run `renglo status` — it prints the next command.

`arbitium` is the same program as `renglo`. Use either name.

---

## What you will have at the end

- Two AWS stacks for this environment: **A** (core platform) and **B** (hub API + websocket)
- One CloudFormation stack per catalog **peer** (`{env}-peer-{peerId}`)
- A verified sender address so the system can send mail
- One admin user in the login pool
- The **first product version** on the hosted API, Amplify console, and peer zips — installed from a **stable BOM** (pins already published to CodeArtifact)
- A **handover folder** at `bootstrap/output/<env-name>/local-dev/` for people who later want a laptop checkout

Until you run §8–§10, the hosted API and Amplify app are empty shells. That is expected after §4. Developers do **not** have to exist for the first version to go live.

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
| **Access to clone** `renglo/bootstrap`, `renglo/launcher`, `renglo/bom-helper`, and `renglo/renglo-cli` (private org repos). Use SSH or HTTPS with a GitHub credential. | |
| **A stable `*-bom` repository** that somebody already cut — for example `YourOrg/acme-bom`. It holds `deploy_targets.yml`, `bom/`, `console_bom/`, and `peers_bom/`. You clone this repo. You do **not** clone `renglo-api`, `console`, or `renglo-lib`. | |
| **GitHub Actions** enabled on that BOM repo, with org access to `bom-helper` (the BOM workflows check it out). The `--github-repo` you pass at init must be this same `ORG/REPO` so Stack A OIDC trusts those workflows. | |


You do **not** clone product apps (`renglo-api`, `console`, `renglo-lib`) or extension repos. Peer CDK reads each handle’s installer contract from the **BOM pin** (downloads that package, uses `installer/infra` or `/infra` inside it).

### Names you must choose now

Write these down. You will type them once.


| Choice                | Rules                                                                                                                                                      |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Env name**          | Short, unique in the account. Letters and digits. Becomes the stack prefix (`acme0922` → `acme0922-stack-a`). Do not reuse a name that already has stacks. |
| **AWS profile**       | The named profile from above.                                                                                                                              |
| **AWS region**        | Usually `us-east-1`.                                                                                                                                       |
| **BOM repo**          | The given `YourOrg/your-bom` (no `.git`). Same repo you clone in §1.                                                                                       |
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

Clone the **given** BOM next to them. The folder name must be the last segment of `--github-repo` (`YourOrg/your-bom` → `your-bom`):

```bash
git clone git@github.com:YourOrg/your-bom.git your-bom
```

If you are already inside a monorepo (`ops/bootstrap`, `ops/launcher`), clone it into `ops/` so it sits next to `launcher`.

You still do **not** clone `renglo-api`, `console`, `renglo-lib`, or extension repos.

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

The hub always runs on Lambda. Peer compute (Fargate / EC2) is chosen later in the BOM catalog, not here.

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

Zip or share **that folder** only if someone later wants a laptop checkout. Developers follow `local-dev/README.md`. They still need an AWS profile that can reach this same account.

This folder does **not** put backend or console code on AWS. The hosted API and Amplify app stay empty until §10.

If you later change stacks or the sender, run `renglo state local-config` again and resend the folder.

Check what was registered:

```bash
renglo state show
renglo stack status
```

---



## 8. Point this environment at the given BOM

The BOM is the pin list. Somebody already cut it and published those versions to CodeArtifact. You do not rebuild that list here, and you do not run git-convoy.

Open `your-bom/`. Confirm `deploy_targets.yml` has a `peers:` catalog, and that `bom/`, `console_bom/`, and `peers_bom/` version files are on disk. Then add **this** environment under `tenants:` if it is not already there. The key must equal `--env-name`. Do not invent pin versions. Do not delete other tenants.

```yaml
tenants:
  acme0922:
    aws_account: "123456789012"   # this account (aws sts get-caller-identity)
    aws_region: us-east-1
```

Commit and push that tenant row on the BOM `main` branch. CI and OIDC only see what is in the GitHub repo. A local-only edit is enough for laptop peer CDK, not for the first product deploy.

Do **not** clone extension repos. `renglo peer list` shows handles; `peer deploy` downloads each handle’s pinned wheel and reads `installer/infra` (or `/infra`) from that package. A local `extensions/<handle>/` tree is only an incubation override.

If `deploy_targets.yml` lists `hub.python` extensions that declare AWS resources, grow Stack B now so those buckets and policies exist before the first hub zip lands:

```bash
renglo system synth
renglo stack deploy --stack b --write-state
```

---



## 9. Peer stacks

Each catalog peer is its own CloudFormation stack (`{env}-peer-{peerId}`). GitHub Actions will later fill the zip (and ECS image). Actions **cannot** create the first stack — that is this laptop step.

```bash
# once per machine (aws-cdk-lib for peer CDK; do not copy this venv)
bash bom-helper/setup-venv.sh

renglo peer list
renglo peer show PEER          # optional
renglo peer deploy --peer-id PEER --write-state
```

Repeat `peer deploy` for every id in `renglo peer list`. `--write-state` refreshes SSM after the stack exists. It does not put handler code on the zip yet.

`peer deploy` fails if the pinned package has no `installer/infra` (older wheels predating this contract). Do not invent pins. Ask for a BOM whose packages were published with installer/infra staged into the wheel, or drop a local `extensions/<handle>/installer/infra` override for incubation.

Do not leave a catalog row without a stack. CI assumes `{env}-peer-{peerId}` already exists.

---



## 10. First product version (BOM CI, no product clones)

The hosted API, Amplify console, and peer zips are filled from **CodeArtifact pins** in the given BOM. The BOM workflows check out `bom-helper` and pull artifacts. Nobody clones `renglo-api`, `console`, or `renglo-lib` for this step.

`--github-repo` from §3 must be this BOM (`YourOrg/your-bom`). Stack A OIDC trusts that repo only.

On GitHub → the BOM repo → **Actions**, run (or re-run) these three workflows for the tenant key you added:

| Workflow | What it installs |
| -------- | ---------------- |
| **Deploy** (`deploy.yml`) | Hub / API Lambda from `bom/vX.Y.Z.json` |
| **Deploy Console** (`deploy_console.yml`) | Amplify console from `console_bom/vX.Y.Z.json` |
| **Deploy Peers** (`deploy_peers.yml`) | Each peer zip (and ECS image) from `peers_bom/<id>/`, then SSM routes |

If `main` already has the pin files, **workflow_dispatch** is enough — you do not need a dummy commit. A push to `main` also works, by path: `bom/**` → Deploy, `console_bom/**` → Deploy Console, `peers_bom/**` or `deploy_targets.yml` → Deploy Peers.

That is the missing middle step. git-convoy is how a **new** BOM is cut later. It is not how you install a BOM you were already given.

When the three workflows are green:

```bash
renglo state show
renglo stack status
renglo peer list
```

The API URL and Amplify URL from `renglo state show` should now serve that BOM version. Sign in with the admin from §5.

If a workflow fails on a missing CodeArtifact version, the given BOM is not installable as-is. Do not invent pins. Ask whoever cut the BOM to publish those versions (or give you a BOM whose pins are already in the registry).

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

# given BOM (folder name = last segment of ORG/BOM)
# add tenants.<NAME> (the key is the env prefix), then push that row on main
renglo peer list
bash bom-helper/setup-venv.sh
renglo peer deploy --peer-id PEER --write-state   # once per catalog peer
# GitHub Actions on ORG/BOM: Deploy, Deploy Console, Deploy Peers
```

Handover (laptop later): `bootstrap/output/NAME/local-dev/`

First hosted version: BOM CI, not a product-repo clone.

---



## If something goes wrong


| Symptom                                           | What to do                                                                                                                      |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `workspace root not found`                        | `cd` to the folder that contains `bootstrap/` and `launcher/`, or pass `--workspace PATH`.                                      |
| `python3.12` / `cdk` / `aws_cdk` fail in `doctor` | Install those tools; re-run `bash bootstrap/setup-venvs.sh`. Do not copy `bootstrap/venv` from another machine.                 |
| `sts` fails                                       | `aws sts get-caller-identity --profile YOUR_PROFILE`. Re-login (SSO) if needed.                                                 |
| Stack already exists                              | You reused `--env-name`. Pick a new name or destroy the old stacks first.                                                       |
| Mail not sending                                  | `renglo email sender-status` and `renglo email allow-status`. Sandbox requires `Success` on both the sender and each recipient. |
| `no *-bom/deploy_targets.yml`                     | Clone the given BOM next to `launcher/` (folder name = last segment of `github_repo`).                                          |
| `No tenant …`                                     | Add a `tenants:` key equal to `--env-name`. Push it if you need CI.                                                             |
| Peer synth: no `installer/infra` in the pin       | That wheel predates shipping infra in the package. Need a republished pin, or a local `extensions/<handle>/installer/infra` override. |
| Deploy workflow cannot assume the OIDC role       | `--github-repo` must be the BOM you are running Actions on. Re-init / re-synth A if it was wrong.                               |
| Deploy fails on a missing CodeArtifact version    | The given pins were never published. Do not invent versions; ask for a BOM that is in the registry.                             |
| Need to start over                                | `renglo peer destroy --peer-id PEER --yes` for each peer, then `renglo system destroy --yes` (B then A).                        |


Full command list: [README.md](README.md). Peer catalog and CI details: [bom-helper PEERS.md](../bom-helper/docs/PEERS.md).