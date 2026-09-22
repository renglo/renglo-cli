# Renglo CLI

`renglo` is the operator command for a Renglo system: bring a tenant up, keep its stacks current, manage sender email and operators, and install extensions.

It is not the release-train tool and not the package publisher. After an extension is product, later versions ride the normal release process.

```bash
renglo help
renglo help system          # one family
renglo status               # where you are, and the next command
renglo doctor               # this machine is ready
```

Every command accepts `--json`. Most commands that change AWS accept `--dry-run`. Destructive steps need `--yes`.

---



## Install

Once per machine. Python 3.12 and the AWS CDK CLI (`npm install -g aws-cdk`) must already be on `PATH`. You also need an AWS CLI profile that can reach the tenant account.

```bash
cd ops/renglo-cli            # or the renglo-cli checkout
bash setup_venv.sh
source renglo-venv/bin/activate
renglo doctor
```

The venv is named `renglo-venv` on purpose. With it active you can run `renglo` from any folder inside the workspace — it walks up until it finds one.

`arbitium` is the same command (`arbitium stack status a`). Re-run `setup_venv.sh` (or `pip install -e .`) so both names land on `PATH`.

Alternatively:

```bash
pipx install --pip-args '--isolated --index-url https://pypi.org/simple' -e /path/to/renglo-cli
```



### Global flags


| Flag               | Meaning                                                                    |
| ------------------ | -------------------------------------------------------------------------- |
| `--json`           | Machine-readable output. Works on every command.                           |
| `--workspace PATH` | Workspace root, if you are not already inside it.                          |
| `--profile NAME`   | AWS CLI profile. Stored on an in-progress install so later steps reuse it. |
| `--region REGION`  | AWS region. Defaults to the active install, then the tenant.               |
| `--dry-run`        | Print what would run. On AWS mutators.                                     |
| `--yes`            | Confirm destroy / push.                                                    |


`renglo status` always prints a `next:` line. If you lose your place, start there.

---



## What you are operating

A Renglo deployment is one **hub** plus any number of **peers**.

```mermaid
flowchart LR
  USER["Users and API clients"] --> HUB["Hub"]
  HUB --> P1["Peer lab"]
  HUB --> P2["Peer audio"]
```



The **hub** is the API every client talks to. It authenticates requests and routes work.

A **peer** is a worker with its own compute and permissions. The hub forwards a job and gets a result back. Peers do not talk to clients.

A **handle** is the short name of an extension (`data`, `schd`, `xyz`). Routing uses the handle. An extension runs in exactly one place: on the hub, or on one peer — never both.

Two platform stacks sit under that:


| Stack | What it is                                   | When you touch it                          |
| ----- | -------------------------------------------- | ------------------------------------------ |
| **A** | Core platform: auth, mail, storage, identity | New tenant, or an explicit core change     |
| **B** | Hub-side extension infrastructure            | Hub-placed extensions, blueprints, hub IAM |


**Stack A is never implied.** Installing an extension updates stack B or a peer stack. If you need stack A, you pass `--stack a` yourself.

GitHub OIDC (so CI can assume a role in this account) is created automatically the first time stack A deploys and the provider is missing. You do not choose a variant.

---



## Jobs



### New tenant

From-scratch operator path (clones, prerequisites, handover folder): [NEW_ENVIRONMENT.md](NEW_ENVIRONMENT.md).

```text
renglo system init --env-name NAME --github-repo ORG/BOM \
  --email-from ADDR --email-identity-type domain
renglo system install start --profile PROFILE
renglo system install apply

renglo email verify-sender
renglo admin create you@example.com
renglo email allow teammate@example.com
renglo state local-config
```

`install apply` builds the account, deploys A then B, and registers running URLs. It **stops before** sender verification and the first admin — those stay explicit.

### Redeploy A and/or B

Day-2 loop after a platform change:

```text
renglo system synth
renglo stack deploy --stack a,b --write-state
```

Safer split:

```text
renglo system synth
renglo stack deploy --stack a
renglo stack deploy --stack b
renglo state write
```

`--write-state` is off by default. Register variables only when you intend to.

### New extension

Decide placement first (hub, existing peer, or a new peer), then:

```text
renglo extension install place HANDLE --peer lab --profile PROFILE
renglo extension install plan
renglo extension install config
renglo extension install pin
renglo extension install publish
renglo extension install deploy
renglo extension install test
renglo extension install push
renglo extension install finish
```

`deploy` never touches stack A. Hub placement deploys stack B; peer placement deploys that peer.

### Update a peer (no new extension)

```text
renglo peer list
renglo peer deploy --peer-id lab --write-state
```



### Tear down

```text
renglo system destroy --yes          # B, then A
renglo stack destroy --stack b --yes
renglo peer destroy --peer-id lab --yes
```

Destroying A while B still exists is refused. Destroy B first, or pass `--stack a,b`.

---



## Command reference



### `renglo help [topic]`

Lists nouns and verbs. `renglo help system` (and `stack`, `state`, `email`, `admin`, `user`, `extension`, `peer`) lists one family. `renglo system help` is the same.

### `renglo status`

Env name, stack A/B health, registered sender and URLs, whether a system install or extension install is in progress, and the next command.

Use this whenever you are unsure.

### `renglo doctor`

Checks this machine: Python 3.12, CDK CLI, the platform venv, AWS `sts` for the chosen profile, and that the workspace looks complete. Extension and peer commands also need the product tree (BOM + `extensions/`).

---



### `system` — new tenant

Minimum workspace: platform only.

#### `renglo system init`

Writes the tenant identity from flags. Does not deploy anything.


| Flag                          | Required | Meaning                                                          |
| ----------------------------- | -------- | ---------------------------------------------------------------- |
| `--env-name NAME`             | yes      | Short name of this installation (stack prefix).                  |
| `--github-repo ORG/BOM`       | yes      | GitHub repo that owns this tenant's pins.                        |
| `--email-from ADDR`           | yes      | Email Address from which the system communicates with its users. |
| `--email-identity-type domain | email`   | yes                                                              |
| `--email-hosted-zone-id ID`   | no       | Route 53 zone, when DNS is automatic.                            |
| `--enable-staging`            | no       | Create a staging environment. Staging should ALWAYS be used.     |
| `--compute-type lambda_only   | fargate  | ec2`                                                             |


Does not place extensions.

#### `renglo system synth`

Generates the CloudFormation apps for this env. Run this after `init`, and again before any later `stack deploy`.

#### `renglo system cdk-bootstrap`

One-time CDK bootstrap of the AWS account/region. Safe to re-run. Needed before the first stack deploy in that account.

#### `renglo system destroy [--yes]`

Tears down stack B, then stack A. Requires `--yes` (or `--dry-run`). Peer stacks are not included — destroy those with `renglo peer destroy`.

#### `renglo system install start --profile PROFILE`

Opens a system-install session. The profile is remembered for the remaining phases.

#### `renglo system install plan`

Read-only. Remaining phases: synth, cdk-bootstrap, OIDC (auto on A), stack A, stack B, register variables. SES and admin are listed as *after* apply, not inside it.

#### `renglo system install apply [--through write-state]`

Runs remaining infra phases up to `--through` (default: register variables). Stops before sender verification and admin create.

Resume by running `apply` again; completed phases are skipped.

---



### `stack` — the loop you rerun



#### `renglo stack status [a|b]`

CloudFormation status for A, B, or both.

#### `renglo stack deploy --stack a|b|a,b`


| `--stack` | What deploys                                                                                                  |
| --------- | ------------------------------------------------------------------------------------------------------------- |
| `a`       | Core platform only. Creates GitHub OIDC if it is missing, unless you pass `--create-github-oidc` to force it. |
| `b`       | Hub extension infrastructure only.                                                                            |
| `a,b`     | A, then B.                                                                                                    |


`--write-state` registers URLs and sender after the deploy. Default **off**. `--dry-run` prints the CDK commands.

You must pass `--stack`. There is no default.

#### `renglo stack destroy --stack a|b|a,b [--yes]`

Same letters. Refuses A-before-B. `--yes` required.

---



### `state` — registered variables

These are the values the running system uses: sender, API URL, console URL.

#### `renglo state show`

Prints `FROM_EMAIL`, `FE_BASE_URL`, `BASE_URL`, `AMPLIFY_CONSOLE_URL`.

#### `renglo state write [--dry-run]`

Publishes those values from the live stacks. Run after a deploy that changed URLs or sender, unless you already passed `--write-state`.

#### `renglo state local-config`

Writes the files needed to run the API and console on this laptop. Do this once after the first install, and again if URLs or pool ids changed.

---



### `email` — sending mail

SES starts in **sandbox**: you can only send to addresses you have allowed. `sender-status` prints the AWS URL for requesting production access; this CLI does not file that ticket.



System Email (a.k.a sender). The address from which all the system communication comes from (invitations, recovery, etc)

#### `renglo email sender-status`

Shows the status of the system email . From-address, DNS mode, verification, sandbox vs production.

#### `renglo email verify-sender`

Waits on / re-checks domain verification, or resends the inbox confirmation when the sender is a single mailbox.



Allowed test emails (until SES becomes production). The addresses that need to be whitelisted with SES before opening it to the general public

#### `renglo email allow ADDRESS`

Sandbox recipient whitelist. The recipient must click the SES confirmation mail. No-op if the account already has production access.

Allow every address you will invite until production access is granted.

#### `renglo email allow-status`

Every SES identity in the account/region, with verification status. Email rows are the addresses that have been sent `verify-email-identity` (the sandbox allow-list). `Pending` means the confirmation mail went out and has not been clicked yet. Domain rows are sender-domain verification.

---



### `admin` — Cognito operators

This is **not** the in-app invite funnel. Self-signup stays disabled. Use this for the first operator (and extra operators who should exist in the user pool before the app is up).

#### `renglo admin create EMAIL`

Creates the Cognito user and prints hosted and local setup URLs (`/invite?setup=admin&email=`). Cognito emails a temporary password. Complete setup at that URL.

#### `renglo admin show EMAIL`

Pool lookup: exists, status, enabled.

---



### `extension` — one-time install of a new feature

Minimum workspace: the product tree (BOM + `extensions/<handle>/`). Stack A and B must already exist. You do not deploy stack A here.

An extension is code + (usually) its own AWS resources + an IAM policy. The policy is attached to **whatever machine runs it**. Hub placement → hub role. Peer placement → that peer's roles only. Access follows placement.

Three placements:

```mermaid
flowchart TD
  Q1{"Needs isolation or heavy deps?"}
  Q1 -->|No| HUB["--hub"]
  Q1 -->|Yes| Q2{"Does a suitable peer exist?"}
  Q2 -->|Yes| PEER["--peer ID"]
  Q2 -->|No| NEW["--new-peer ID"]
```




| Placement     | Flag               | What happens                                                |
| ------------- | ------------------ | ----------------------------------------------------------- |
| Hub           | `--hub`            | Code ships inside the API. Use sparingly: one blast radius. |
| Existing peer | `--peer lab`       | Joins that peer's package and roles. Most common.           |
| New peer      | `--new-peer audio` | New worker stack that initially hosts only this handle.     |


`--compute` (`fargate`, `ec2`, `lambda_only`) and `--task-size` apply to `--new-peer`. `lambda_only` has no container runners.

Before `place`: the handle's installer files and a buildable Python package must already exist under `extensions/<handle>/`. Declaring a bucket does not grant access — the policy document must list the actions.

The install is a sheet: `placed → configured → pinned → published → deployed → tested → pushed`, then `finish` clears it. `plan` does not advance the sheet.

#### `renglo extension status`

Current incubation, if any, and the next command. Works with no sheet: tells you to `place`.

#### `renglo extension show HANDLE`

Owner, package name, product vs incubating, installer files present.

#### `renglo extension tree`

Every catalog handle and the machine that owns it.

#### `renglo extension install place HANDLE --hub|--peer PEER|--new-peer PEER --profile PROFILE`

Starts the install. Refuses if the handle is already in the catalog or already product. Marks the extension incubating so release trains skip it until `finish`.

`--profile` is stored and reused. Optional: `--region`, `--python-version`, `--npm`, `--compute`, `--task-size`.

#### `renglo extension install plan`

Read-only preview of catalog edits, the pin it will create, and the deploy it will run.

#### `renglo extension install config`

Records placement. Does not change tenant identity. Does not deploy.

#### `renglo extension install pin [--python-version X.Y.Z] [--npm-version X.Y.Z]`

Creates a **new** version file and points the catalog at it. Never edits the current pin in place. Default Python version comes from the package.

#### `renglo extension install publish [--skip-upload]`

Builds the first wheel and uploads it. Later versions are the publisher + release train, not this command. `--skip-upload` builds only.

#### `renglo extension install deploy [--dry-run]`

Creates the extension's buckets, indexes, and IAM, attaches the policy to the owning machine, then registers routes/variables.


| Placement     | What deploys                      |
| ------------- | --------------------------------- |
| Hub           | Stack B                           |
| Existing peer | That peer stack                   |
| New peer      | The new peer stack (created here) |


**Never stack A.** `--dry-run` prints the commands.

#### `renglo extension install test [--skip-synth]`

Installer files present, and the handle has exactly one owner. A handle on both the hub and a peer (or two peers) fails here.

#### `renglo extension install push [--yes] [--no-push]`

Commits and pushes the BOM. That is the only hand-push for this extension; afterwards the release train owns it. `--yes` skips the prompt. `--no-push` commits locally only.

#### `renglo extension install finish`

Marks the extension product, refreshes membership, deletes the sheet. Refuses unless `test` passed and you have pushed.

Do not run `pin` / `publish` / `push` again for this handle. The CLI refuses once it is product.

---



### `peer` — update a worker without an incubation sheet

Same helper `extension install deploy` uses on a peer path. Use these when the peer already exists and you are not installing a new handle.

#### `renglo peer list`

Every peer, compute mode, and the handles on it.

#### `renglo peer show PEER`

One peer: compute, extensions, pin pointer.

#### `renglo peer synth --peer-id PEER`

Generate that peer's CloudFormation app.

#### `renglo peer deploy --peer-id PEER [--write-state] [--dry-run]`

Deploy (or update) that peer stack. `--write-state` refreshes routes/variables. Does not touch stack A or other peers.

#### `renglo peer destroy --peer-id PEER [--yes]`

Tear that peer stack down. `--yes` required.

---



## What this CLI does not do

- Release trains, hotfixes, or BOM regeneration (that is the convoy / publisher path)
- Publishing wheels after the first one
- Filing the SES production-access request (`sender-status` prints the URL)
- Operator IAM policy helpers
- Overflow teardown or Amplify deploy

