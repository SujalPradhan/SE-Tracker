# Deployment

SE-Tracker runs on one small Google Cloud VM. Gunicorn serves the Flask app,
and Caddy sits in front of it and handles HTTPS. The SQLite database is on
the VM's disk, and a cron job copies it to Cloud Storage every night. There's
no managed database or container setup to look after.

## What's running now

| | |
|---|---|
| URL | https://34-100-168-34.sslip.io |
| VM | `se-tracker`: e2-micro, `asia-south1-a` (Mumbai), Debian 12 |
| IP | static, `se-tracker-ip` |
| App | `/srv/se-tracker` (a git clone of this repo) |
| Config | `/etc/se-tracker.env` |
| Database | `/var/lib/se-tracker/se_tracker.db` |
| Backups | nightly to a Cloud Storage bucket, kept for 30 days |
| Cost | about $10–12 a month (VM, disk and IP) |

We picked Mumbai over the free US-region e2-micro because it's roughly 30 ms
from India, compared with about 250 ms from the US. An e2-micro has plenty of
headroom for a few dozen TAs.

## Day-to-day

**Ship a change.** Push to `main`, then:

```sh
gcloud compute ssh se-tracker --zone=asia-south1-a -- \
  'cd /srv/se-tracker && sudo -u setracker git pull \
   && sudo -u setracker .venv/bin/pip install -q -r requirements.txt \
   && sudo systemctl restart se-tracker'
```

**Check it's healthy.**

```sh
gcloud compute ssh se-tracker --zone=asia-south1-a -- \
  'systemctl is-active se-tracker caddy; sudo journalctl -u se-tracker -n 20 --no-pager'
```

**Take a backup now.** Run `sudo /usr/local/bin/se-tracker-backup` on the VM.

**Restore a backup.**

```sh
gcloud storage ls gs://BUCKET_NAME/se-tracker/
# then on the VM:
sudo systemctl stop se-tracker
gcloud storage cp gs://BUCKET_NAME/se-tracker/se_tracker-YYYYMMDD-HHMMSS.db.gz /tmp/
gunzip -c /tmp/se_tracker-*.db.gz | sudo -u setracker tee /var/lib/se-tracker/se_tracker.db >/dev/null
sudo systemctl start se-tracker
```

## Setting it up from scratch

You'll need the [gcloud CLI](https://cloud.google.com/sdk/docs/install) and a
project with billing turned on. Replace `PROJECT_ID`, `PROJECT_NUMBER` and
`BUCKET_NAME` below. Bucket names are global, so pick something unique.

### 1. VM, static IP and firewall

```sh
gcloud config set project PROJECT_ID
gcloud services enable compute.googleapis.com storage.googleapis.com

gcloud compute addresses create se-tracker-ip --region=asia-south1
gcloud compute addresses describe se-tracker-ip --region=asia-south1 --format='value(address)'

gcloud compute instances create se-tracker \
  --zone=asia-south1-a --machine-type=e2-micro \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=10GB --boot-disk-type=pd-balanced \
  --address=se-tracker-ip --tags=se-tracker-web \
  --scopes=default,storage-rw

gcloud compute firewall-rules create se-tracker-allow-web \
  --allow=tcp:80,tcp:443 --target-tags=se-tracker-web
```

For the hostname, either point a domain's `A` record at the IP, or use the
free `<ip-with-dashes>.sslip.io` (e.g. `34-100-168-34.sslip.io`). Caddy gets
the HTTPS certificate on its own either way.

### 2. Backup bucket

```sh
gcloud storage buckets create gs://BUCKET_NAME --location=asia-south1
echo '{"rule":[{"action":{"type":"Delete"},"condition":{"age":30}}]}' > lifecycle.json
gcloud storage buckets update gs://BUCKET_NAME --lifecycle-file=lifecycle.json

# the VM's default service account needs to write to it
gcloud storage buckets add-iam-policy-binding gs://BUCKET_NAME \
  --member=serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com \
  --role=roles/storage.objectAdmin
```

### 3. Install on the VM

```sh
gcloud compute ssh se-tracker --zone=asia-south1-a
curl -fsSLO https://raw.githubusercontent.com/SujalPradhan/SE-Tracker/main/deploy/gcp/setup.sh
sudo bash setup.sh https://github.com/SujalPradhan/SE-Tracker.git
sudo nano /etc/se-tracker.env      # set SITE_ADDRESS and BACKUP_BUCKET
sudo systemctl restart se-tracker caddy
```

`setup.sh` adds swap, installs Python and Caddy, creates a `setracker` user,
clones the repo, writes a fresh `SECRET_KEY`, and installs the systemd
service and the nightly backup cron job. You can run it again safely.

### 4. Google sign-in for `/admin`

This part has to be done in the Cloud Console. gcloud can't create OAuth
clients.

1. Go to **Google Auth Platform → Branding**. Set the app name to
   "SE-Tracker" and add a support email.
2. Under **Audience**, choose **External**, then click **Publish app**. We
   only ask for name and email, so Google doesn't need to review it.
3. Under **Clients**, create a **Web application** client with the redirect
   URI `https://<your-host>/admin/callback`.
4. Put the client ID and secret in `/etc/se-tracker.env`, then run
   `sudo systemctl restart se-tracker`.

Only the emails in `DEFAULT_ADMIN_EMAILS` in `admin.py` can get in. You can
override that list with `ADMIN_EMAILS`. The list is checked on every request,
so removing someone locks them out right away.

## Settings (`/etc/se-tracker.env`)

| Variable | What it's for |
|---|---|
| `SITE_ADDRESS` | Hostname Caddy serves and gets a certificate for |
| `SECRET_KEY` | Signs sessions (`setup.sh` generates one) |
| `DATABASE_URL` | `sqlite:////var/lib/se-tracker/se_tracker.db` |
| `HTTPS_ONLY=1` | Session cookies only over HTTPS |
| `BEHIND_PROXY=1` | Trust Caddy's forwarded headers (the Google redirect needs this) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Admin sign-in |
| `ADMIN_EMAILS` | Optional comma-separated replacement for the admin allowlist |
| `BACKUP_BUCKET` | Where nightly backups go |

## The old PythonAnywhere site

MAY2026 ran on PythonAnywhere. SEP2026 started with an empty database, so
accounts didn't carry over, and every TA registers again on the new site. To
retire the old one, delete `~/SE-Tracker/se_tracker.db` on PythonAnywhere,
then disable the web app from its **Web** tab.
