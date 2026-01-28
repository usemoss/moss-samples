# Moss Next.js Demo

A modern semantic search interface built with Next.js 15, React, and Moss SDK.

This demo showcases how to use **Server Actions** to securely interact with Moss from a web application.

## 🚀 Features

- **Sub-10ms Retrieval**: Experience Moss's industry-leading speed in a browser.
- **Server Actions**: Secure implementation that keeps your API keys on the server.
- **Glassmorphism UI**: A sleek, responsive dark-mode interface.
- **Real-time Stats**: View retrieval time and match confidence scores.

## ⚙️ Setup

1. **Install Dependencies**:

   ```bash
   npm install
   ```

2. **Configure Environment**:
   Copy the example and fill in your credentials from the [Moss Portal](https://portal.usemoss.dev):

   ```bash
   cp .env.example .env.local
   ```

   Required variables:
   - `MOSS_PROJECT_ID`
   - `MOSS_PROJECT_KEY`
   - `MOSS_INDEX_NAME`

3. **Run Development Server**:
   ```bash
   npm run dev
   ```
   Open [http://localhost:3000](http://localhost:3000) in your browser.

## 📁 Structure

- `app/page.tsx`: The main UI component (Client Side).
- `app/actions.ts`: Moss logic and Server Actions (Server Side).
- `app/globals.css`: Premium styling and glassmorphism definitions.

## 🛠️ Integration Guide

To add Moss to your own Next.js app:

1. Install the SDK: `npm install @inferedge/moss`
2. Create a Server Action (see `app/actions.ts`).
3. Call the action from your React components.
