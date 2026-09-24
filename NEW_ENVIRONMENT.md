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

After §4 the platform runs but carries no application code: the hosted API serves a placeholder, the Amplify app has never built, and no peer stack exists yet. §8–§10 fix that, in that order. Developers do **not** have to exist for the first version to go live.

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


| Need                                                                                                                                                                                                                                                     | Why |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --- |
| **Access to clone** `renglo/bootstrap`, `renglo/launcher`, `renglo/bom-helper`, and `renglo/renglo-cli` (private org repos). Use SSH or HTTPS with a GitHub credential.                                                                                  |     |
| **A stable `*-bom` repository** that somebody already cut — for example `YourOrg/acme-bom`. It holds `deploy_targets.yml`, `bom/`, `console_bom/`, and `peers_bom/`. You clone this repo. You do **not** clone `renglo-api`, `console`, or `renglo-lib`. |     |
| **GitHub Actions** enabled on that BOM repo, with org access to `bom-helper` (the BOM workflows check it out). The `--github-repo` you pass at init must be this same `ORG/REPO` so Stack A OIDC trusts those workflows.                                 |     |


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

## 8. Register this environment in the BOM

Everything so far built empty infrastructure. Stack A and Stack B are running, mail works, and you have an admin — but no application code is on AWS. The hub API Lambda still answers with the placeholder image Stack A seeded, the Amplify console has never built, and the peers have no stacks at all. §8 and §9 get this environment ready; §10 installs the code.

The BOM repo is the version list for the platform. Somebody already cut it and published every version it names to CodeArtifact. You do not rebuild it, you do not run git-convoy, and you do not clone product or extension repos.

Open `your-bom/` and confirm these are on disk:


| Path                         | What it pins                                                                                                                                       |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `deploy_targets.yml`         | Which extensions ride the hub image (`hub:` → `python:`), which peers exist (`peers:`), and which environments this BOM installs into (`tenants:`) |
| `bom/vX.Y.Z.json`            | Package versions for the hub / API Lambda                                                                                                          |
| `console_bom/vX.Y.Z.json`    | Package versions for the Amplify console                                                                                                           |
| `peers_bom/<id>/vX.Y.Z.json` | Package versions for one peer                                                                                                                      |


### Add this environment to `tenants:`

CI installs a BOM only into the environments that BOM lists. Add yours. The key must be exactly the `--env-name` from §3, because that same string is the AWS stack prefix. Do not change pin versions. Do not delete other tenants.

```yaml
tenants:
  acme0922:
    aws_account: "123456789012"   # this account: aws sts get-caller-identity
    aws_region: us-east-1
    stages:
      staging:
        enabled: true
      production:
        enabled: false
```

The `stages:` block is required. A tenant without one is skipped by every workflow in §10 — the run prints `Skipping invalid tenant config` and stays green, so nothing tells you it was ignored. Leave `production` disabled until you actually want a production deploy.

Save the file and stop there. Do not commit or push it yet:

- §9 runs on this laptop and reads `deploy_targets.yml` from disk, so a local edit is all it needs.
- A push that touches `deploy_targets.yml` starts all three CI workflows, and they install code into peer stacks that do not exist until §9 is finished.

§10 is where you push.

### See which peers this BOM declares

```bash
renglo peer list
```

The first line is your environment name. Each line after it is one peer from the `peers:` catalog — its id, its compute type, and the extension handles assigned to it:

```text
acme0922
  lab              fargate      acmelab, acmetriage
```

That is a declaration, not an installation. This command and `renglo peer show lab` both only read the YAML file. None of these peers exist in AWS yet: no `acme0922-peer-lab` stack, no peer role, no peer Lambda. `renglo stack status` still lists stacks A and B only. §9 creates them.

You do not clone repos for those handles. In §9, peer CDK downloads each handle's pinned package from CodeArtifact and reads the `installer/infra` folder from inside that package.

### Leave Stack B alone

§4 synthesized and deployed Stack B, and that synth already read this same `deploy_targets.yml`. The buckets, indexes, and IAM policies for extensions on `hub:` `python:` are in that stack. Adding a tenant row changes nothing there, so do not run `renglo system synth` or `renglo stack deploy --stack b` again. You only re-synth and redeploy B later, if someone changes which extensions ride the hub image.

---

## 9. Build the peer infrastructure

A peer is an independently provisioned worker service: its own IAM role, its own Lambda, an ECS cluster when its compute is `fargate` or `ec2`, plus whatever buckets and vector indexes its extensions declare. Each peer gets its own CloudFormation stack, named `{env}-peer-{peerId}` — `acme0922-peer-lab` for the example above.

You create those stacks here, from this laptop. The §10 workflows can only update code inside a peer stack that already exists; they cannot create one.

Build the peer CDK environment once per machine:

```bash
bash bom-helper/setup-venv.sh
```

That creates `bom-helper/bom-venv` with `aws-cdk-lib`. Do not copy it from another computer.

Then run this once per peer id you saw in §8:

```bash
renglo peer deploy --peer-id lab --write-state
```

Each run does four things:

1. Reads your tenant row from `deploy_targets.yml` for the AWS account and region.
2. Downloads the pinned package of every handle on that peer and extracts `installer/infra` — the contract that declares the peer's buckets, indexes, and IAM policy.
3. Deploys `{env}-peer-{peerId}`: role, policies, declared storage, an ECS cluster when compute is `fargate` or `ec2`, and a placeholder Lambda.
4. `--write-state` refreshes SSM so the hub knows how to route to that peer.

Add `--dry-run` to print the CDK command without deploying anything.

Check each stack landed:

```bash
renglo peer status --profile YOUR_PROFILE
```

Each declared peer prints its CloudFormation stack name and status. You want `CREATE_COMPLETE` (or `UPDATE_COMPLETE` on a later run). The peer's Lambda is still a placeholder — handler code arrives in §10.

`renglo stack status --profile YOUR_PROFILE` and `renglo status --profile YOUR_PROFILE` include the same peer rows alongside stacks A and B.

Two failures stop this step:

- `No tenant 'acme0922' in deploy_targets.yml` — the row from §8 is missing, or its key does not match `--env-name` exactly.
- No `installer/infra` in a pinned package — that wheel was published before packages carried their infra contract. Do not invent a different pin. Ask for a BOM whose packages were published with `installer/infra` inside them.

Give every peer in the catalog a stack before you move on. §10 assumes `{env}-peer-{peerId}` already exists for each one.

---

## 10. Install the first product version

This is the step that puts application code on AWS. Three GitHub Actions workflows in the BOM repo read the pin files, pull those packages from CodeArtifact, and install them onto the infrastructure you built. 

Check two things first: every peer stack from §9 is `CREATE_COMPLETE`, and the `--github-repo` you passed in §3 is this exact BOM repo. Stack A's OIDC role trusts that one repository, so workflows in any other repo cannot get credentials for your account.

### Push the tenant row

The workflows read the repo on GitHub, not your laptop. Push what you edited in §8:

```bash
cd your-bom
git add deploy_targets.yml
git commit -m "Add tenant acme0922"
git push origin main
```

`deploy_targets.yml` is a trigger path for all three workflows, so that one push starts all of them:


| Name in the Actions list                           | File                 | What it installs                                                            |
| -------------------------------------------------- | -------------------- | --------------------------------------------------------------------------- |
| **Deploy Backend (Staging -> Production tenants)** | `deploy.yml`         | Hub / API Lambda, from `bom/vX.Y.Z.json`                                    |
| **Deploy Console (Amplify)**                       | `deploy_console.yml` | Amplify console, from `console_bom/vX.Y.Z.json`                             |
| **Deploy Peers**                                   | `deploy_peers.yml`   | Each peer's zip (and ECS image) from `peers_bom/<id>/`, then the SSM routes |


Watch them on GitHub → the BOM repo → **Actions**. Two things to expect from that run:

- Each workflow runs for **every** tenant with an enabled stage, not only yours. The other tenants are reinstalled at the versions already on `main`, so nothing new ships to them, but their jobs do run.
- Only Deploy Peers can be narrowed on a rerun: dispatch it with the `tenant` and `peer` inputs. Deploy Backend takes only `skip_production` and Deploy Console takes no inputs, so rerunning either one covers all tenants.

Later on, pushes trigger by path: `bom/**` → Deploy Backend, `console_bom/**` → Deploy Console, `peers_bom/**` → Deploy Peers, `deploy_targets.yml` → all three. When the pins and your tenant row are already on `main`, **Run workflow** (workflow_dispatch) is enough; you never need a dummy commit.

### Confirm the environment is live

When the three workflows are green:

```bash
renglo state show
```

That prints `BASE_URL` (the hosted API) and `AMPLIFY_CONSOLE_URL` (the console), now serving the versions this BOM pins. Open the console URL and sign in with the admin you created in §5.

If a workflow fails because a CodeArtifact version does not exist, the BOM you were given is not installable as-is. Do not edit the pins to versions that do exist. Ask whoever cut the BOM to publish the missing ones, or to hand you a BOM whose pins are all in the registry.

git-convoy is the tool for cutting a **new** BOM later. It plays no part in installing a BOM you were given.

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
# 1. add tenants.<NAME> with a stages: block — save it, do not push yet
renglo peer list                                 # what the catalog declares
bash bom-helper/setup-venv.sh                    # once per machine
renglo peer deploy --peer-id PEER --write-state  # once per catalog peer
# 2. git push that tenant row on main — starts all three BOM workflows
renglo state show                                # API + console URLs
```

Handover (laptop later): `bootstrap/output/NAME/local-dev/`

First hosted version: BOM CI, not a product-repo clone.

---

## If something goes wrong


| Symptom                                           | What to do                                                                                                                             |
| ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `workspace root not found`                        | `cd` to the folder that contains `bootstrap/` and `launcher/`, or pass `--workspace PATH`.                                             |
| `python3.12` / `cdk` / `aws_cdk` fail in `doctor` | Install those tools; re-run `bash bootstrap/setup-venvs.sh`. Do not copy `bootstrap/venv` from another machine.                        |
| `sts` fails                                       | `aws sts get-caller-identity --profile YOUR_PROFILE`. Re-login (SSO) if needed.                                                        |
| Stack already exists                              | You reused `--env-name`. Pick a new name or destroy the old stacks first.                                                              |
| Mail not sending                                  | `renglo email sender-status` and `renglo email allow-status`. Sandbox requires `Success` on both the sender and each recipient.        |
| `no *-bom/deploy_targets.yml`                     | Clone the given BOM next to `launcher/` (folder name = last segment of `github_repo`).                                                 |
| `No tenant …`                                     | Add a `tenants:` key equal to `--env-name` and save it locally before §9. Push that row on `main` in §10, after the peer stacks exist. |
| Workflow is green but installed nothing           | `Skipping invalid tenant config` in the log: your `tenants.<NAME>` row has no `stages:` block with an enabled stage.                   |
| Deploy Peers fails: no such stack                 | That catalog peer never got `renglo peer deploy` in §9. CI updates peer stacks; it does not create them.                               |
| Peer synth: no `installer/infra` in the pin       | That wheel predates shipping infra in the package. Ask for a BOM whose packages were published with installer/infra in the wheel.      |
| Deploy workflow cannot assume the OIDC role       | `--github-repo` must be the BOM you are running Actions on. Re-init / re-synth A if it was wrong.                                      |
| Deploy fails on a missing CodeArtifact version    | The given pins were never published. Do not invent versions; ask for a BOM that is in the registry.                                    |
| Need to start over                                | `renglo peer destroy --peer-id PEER --yes` for each peer, then `renglo system destroy --yes` (B then A).                               |


Full command list: [README.md](README.md). Peer catalog and CI details: [bom-helper PEERS.md](../bom-helper/docs/PEERS.md).