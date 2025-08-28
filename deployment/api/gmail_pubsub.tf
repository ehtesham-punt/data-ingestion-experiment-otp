provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Pub/Sub Topic for Gmail Push
resource "google_pubsub_topic" "gmail" {
  name = "gmail-raw-emails"
}

# 2. Pub/Sub Push Subscription
resource "google_pubsub_subscription" "gmail_push" {
  name  = "gmail-notify-sub"
  topic = google_pubsub_topic.gmail.id

  push_config {
    push_endpoint = "https://your-service-url/pubsub/gmail-notify"
    oidc_token {
      service_account_email = var.push_auth_service_account
    }
  }
}

# 3. IAM: Let Gmail push to topic
resource "google_pubsub_topic_iam_member" "gmail_publisher" {
  topic = google_pubsub_topic.gmail.name
  role  = "roles/pubsub.publisher"
  member = "serviceAccount:gmail-api-push@system.gserviceaccount.com"
}
