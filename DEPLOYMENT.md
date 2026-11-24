# 🚀 Complete Multi-Cloud Deployment Guide (Netlify + Render)
*Updated: November 24, 2026*

This guide walks you through deploying your **Clipper AI** application across a free multi-cloud architecture:
- **Frontend UI**: Hosted globally on **Netlify** (0ms cold start, ultra-fast CDN).
- **Backend API**: Hosted on **Render.com** (Free Web Service running Docker with Python, FFmpeg, Whisper & Gemini Flash).

---

## 📋 Overview of Steps

1. **Step 1**: Push your code to a new GitHub repository.
2. **Step 2**: Deploy the Backend to **Render.com** (Docker Web Service).
3. **Step 3**: Deploy the Frontend to **Netlify** (Netlify Drop or GitHub).
4. **Step 4**: Connect Netlify to your Render backend URL.

---

## Step 1: Push Code to GitHub

Open PowerShell in your project folder (`c:\Users\sharm\OneDrive\Desktop\clip_gta6`):

```powershell
cd C:\Users\sharm\OneDrive\Desktop\clip_gta6

# 1. Initialize git
git init

# 2. Add files (the .gitignore automatically protects your .env and .venv)
git add .

# 3. Create initial commit
git commit -m "Clipper AI multi-cloud deployment setup"

# 4. Rename default branch to main
git branch -M main

# 5. Link to your GitHub repository (replace with your repo URL)
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/<YOUR_REPO_NAME>.git

# 6. Push code
git push -u origin main
```

---

## Step 2: Deploy Backend to Render.com (100% Free)

1. Open **[Render.com](https://render.com)** and sign in with your GitHub account.
2. In the Render Dashboard, click **New +** (top right) and select **Web Service**.
3. Choose **Build and deploy from a Git repository** and select your `clip_gta6` repository.
4. Fill in the service configuration:
   - **Name**: `clipper-backend` (or any name you choose)
   - **Region**: Choose the closest region to you (e.g., Singapore, Frankfurt, Oregon)
   - **Branch**: `main`
   - **Root Directory**: *(leave blank)*
   - **Runtime**: Select **Docker** (Render will automatically detect your `Dockerfile`)
   - **Instance Type**: Select **Free** ($0/month)
5. Scroll down to **Environment Variables** and click **Add Environment Variable**:
   - **Key**: `GEMINI_API_KEY`
   - **Value**: *(paste your Google AI Studio API key)*
6. Click **Deploy Web Service** at the bottom.
7. Render will build the Docker container (installing FFmpeg, faster-whisper, and uvicorn).
8. Once finished, Render will display your live public backend URL at the top:  
   👉 `https://clipper-backend-xxxx.onrender.com`

---

## Step 3: Deploy Frontend to Netlify (Takes 30 Seconds)

You have two simple ways to deploy to Netlify:

### Method A: Netlify Drop (Fastest — No Git required for frontend)
1. Open **[Netlify Drop](https://app.netlify.com/drop)** in your browser.
2. Open Windows File Explorer and navigate to `C:\Users\sharm\OneDrive\Desktop\clip_gta6`.
3. Drag and drop the **`frontend`** folder directly into the Netlify upload area.
4. Netlify will publish your site in ~10 seconds and give you a live URL:  
   👉 `https://<your-site-name>.netlify.app`

### Method B: Netlify via GitHub (Auto-updates on Git push)
1. In your **[Netlify Dashboard](https://app.netlify.com)**, click **Add new site** > **Import an existing project**.
2. Select **GitHub** and authorize your repository.
3. Under **Build settings**:
   - **Base directory**: *(leave blank)*
   - **Build command**: *(leave blank)*
   - **Publish directory**: `frontend`
4. Click **Deploy site**.

---

## Step 4: Connect Netlify Frontend to Render Backend

1. Open your live Netlify website (`https://<your-site-name>.netlify.app`).
2. When the site loads for the first time, it will automatically prompt you for your backend URL (or click the **⚙️ Settings** icon in the top right navbar).
3. Paste your Render backend URL (e.g. `https://clipper-backend-xxxx.onrender.com`).
4. Click **Test Connection** (it will test `/api/health` and show a green *"Connected!"* badge).
5. Click **Save & Apply**.

---

## 🎉 Done! How to Use Your Live App

1. Visit your Netlify website URL.
2. Paste any YouTube video link.
3. Choose your number of clips (e.g., 3 or 5) and duration.
4. Click **Generate Viral Clips**.
5. Watch the real-time progress bar.
6. Preview the vertical 9:16 clips with loud, synchronized karaoke subtitles and click **Download Clip (.mp4)**!

---

### 💡 Note About Free Tier Sleep on Render:
- Render's free tier spins down (sleeps) after 15 minutes of inactivity.
- If it hasn't been used in a while, your first video request may take ~30–45 seconds while Render boots the container.
- Thanks to the **Multi-Cloud** setup, your Netlify frontend will always load **instantly (in under 100ms)**!
