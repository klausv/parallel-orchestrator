# Android Voice Control Setup

This guide explains how to trigger parallel Claude tasks from your Android phone using voice commands.

## Option 1: GitHub Mobile App (Simplest)

### Setup
1. Install **GitHub Mobile** from Play Store
2. Sign in to your GitHub account
3. Enable notifications for Actions

### Usage
1. Open GitHub Mobile
2. Navigate to your repository → Actions
3. Tap on "Parallel Claude Tasks" workflow
4. Tap "Run workflow"
5. Enter your task description
6. Tap "Run"

### Notifications
- Enable push notifications in GitHub Mobile settings
- You'll receive notifications when workflows complete

---

## Option 2: Tasker + HTTP Request (Voice Control)

### Prerequisites
- Tasker app (paid, ~$3.50)
- GitHub Personal Access Token with `repo` and `workflow` permissions

### Create GitHub Token
1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token with scopes:
   - `repo` (full control)
   - `workflow` (update GitHub Action workflows)
3. Copy the token (you won't see it again)

### Tasker Setup

#### Task: Trigger Claude Workflow

1. Open Tasker → Tasks → + (add task) → Name: "Run Claude Task"

2. Add action: **Net → HTTP Request**
   ```
   Method: POST
   URL: https://api.github.com/repos/YOUR_USERNAME/YOUR_REPO/actions/workflows/parallel-tasks.yml/dispatches
   Headers:
     Authorization: Bearer YOUR_GITHUB_TOKEN
     Accept: application/vnd.github.v3+json
     Content-Type: application/json
   Body: {"ref":"main","inputs":{"task_description":"%par1","num_workers":"2"}}
   ```

3. Add action: **Alert → Flash**
   ```
   Text: Claude task started: %par1
   ```

#### Profile: Voice Trigger

1. Create new Profile → Event → AutoVoice Recognized
   (Requires AutoVoice plugin, free version works)

2. Command filter: `run claude task *`

3. Link to "Run Claude Task" task with parameter:
   ```
   %avcomm (the captured voice text after "run claude task")
   ```

### Alternative: Google Assistant Routine

If you don't want to use Tasker:

1. Create a Google Assistant Routine
2. Trigger: "Run my AI task"
3. Action: Open app → Tasker → Run task "Run Claude Task"

---

## Option 3: IFTTT (Easiest Voice Control)

### Setup

1. Install IFTTT app
2. Create new Applet:

**IF**: Google Assistant → Say a phrase with a text ingredient
- What do you want to say? "Run claude task $"
- What's another way to say it? "Start AI task $"
- What do you want the Assistant to say in response? "Starting Claude task"

**THEN**: Webhooks → Make a web request
- URL: `https://api.github.com/repos/YOUR_USERNAME/YOUR_REPO/actions/workflows/parallel-tasks.yml/dispatches`
- Method: POST
- Content Type: application/json
- Additional Headers: `Authorization: Bearer YOUR_GITHUB_TOKEN`
- Body: `{"ref":"main","inputs":{"task_description":"{{TextField}}","num_workers":"2"}}`

### Usage
Say: "Hey Google, run Claude task implement user login"

---

## Option 4: Pushover Notifications (Results)

Get notifications when tasks complete:

### Setup
1. Create account at pushover.net
2. Install Pushover app on Android
3. Note your User Key and create an API Token

### Add to GitHub Secrets
- `PUSHOVER_USER`: Your user key
- `PUSHOVER_TOKEN`: Your API token

The workflow will automatically send push notifications when complete.

---

## Quick Reference

| Method | Voice Control | Effort | Cost |
|--------|---------------|--------|------|
| GitHub Mobile | No | Low | Free |
| Tasker | Yes | Medium | ~$3.50 |
| IFTTT | Yes | Low | Free (limited) |

## Troubleshooting

### Workflow not triggering
- Check that the token has `workflow` permission
- Verify the workflow file path is correct
- Check GitHub Actions is enabled for the repo

### No notifications
- Enable GitHub Mobile notifications in Android settings
- Check Pushover is configured correctly in GitHub secrets

### Voice command not recognized
- Ensure AutoVoice has accessibility permissions
- Try simpler command phrases
- Check Tasker is not being killed by battery optimization

---

## Security Notes

- Store your GitHub token securely (Tasker's encrypted variables)
- Use a token with minimal required permissions
- Consider creating a dedicated GitHub bot account for automation
- Regularly rotate your tokens
