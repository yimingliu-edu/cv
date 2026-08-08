# GitHub Username Rename Guide: `888dddhhh` → `eduliuym`

This document walks through renaming the GitHub account that owns the
[Yiming Liu personal site](https://github.com/888dddhhh/Lym) from
`888dddhhh` to `eduliuym`, so the GitHub Pages URL becomes
**`eduliuym.github.io/Lym`** instead of `888dddhhh.github.io/Lym`.

---

## 0. Before you start

- Make sure the new username **`eduliuym`** is currently available.
  Try visiting <https://github.com/eduliuym> — if the page exists
  (even a 404 page with that name claimed), you'll need to pick a
  different name.
- Pick a quiet 30-minute window. Renaming touches every clone of every
  repo, and you may want to update local checkouts afterwards.
- Notify any collaborators on other repos. They will need to update
  their remotes.

---

## 1. Rename the GitHub account

1. Sign in to GitHub as the account that currently owns the site
   (currently `888dddhhh`).
2. Click your avatar (top right) → **Settings**.
3. In the left sidebar, click **Account**.
4. Scroll to the **Change username** section at the bottom.
5. Type `eduliuym` and follow the prompts.
6. GitHub will warn you about:
   - **Redirects** — old URLs (`888dddhhh.github.io/Lym`) automatically
     301-redirect to the new ones (`eduliuym.github.io/Lym`).
     Inbound links and SEO are preserved.
   - **Renaming cannot be undone for 6 months** if you decide you want
     to reclaim `888dddhhh` later (only if it wasn't taken by someone
     else in the meantime).
7. Confirm. GitHub will sign you out and back in.

After the rename:

| Old | New |
|---|---|
| `https://github.com/888dddhhh/Lym` | `https://github.com/eduliuym/Lym` |
| `https://888dddhhh.github.io/Lym` | `https://eduliuym.github.io/Lym` |
| `git@github.com:888dddhhh/Lym.git` | `git@github.com:eduliuym/Lym.git` |

---

## 2. Update your local clone

In any local working copy of the repo, including the one WorkBuddy
uses at `~/Documents/LYM Website/lym-site`:

```bash
cd "/Users/keanu/Documents/LYM Website/lym-site"
git remote set-url origin https://github.com/eduliuym/Lym.git
# or, if you use SSH:
git remote set-url origin git@github.com:eduliuym/Lym.git

# verify
git remote -v
```

Then pull once to make sure the new origin works:

```bash
git pull
```

---

## 3. Re-enable GitHub Pages on the new repo

GitHub Pages settings are **per-repo**, not per-user, and they
*should* survive a rename — but Pages occasionally gets re-disabled
during a rename. Verify it:

1. Visit the new repo page: `https://github.com/eduliuym/Lym`
2. **Settings → Pages**
3. Confirm:
   - **Source:** `Deploy from a branch`
   - **Branch:** `main` / `(root)`
4. If it's off, re-enable it. The site will be live within a minute or
   two at `https://eduliuym.github.io/Lym/`.

---

## 4. Update the deploy script

`deploy-to-github.sh` already uses `origin` so it will keep working
after the rename — no edits required. But if it ever hard-coded the
old URL (it doesn't currently), update it.

---

## 5. Update inbound links (optional but nice)

If you have shared the site URL anywhere — email signature, CV,
LinkedIn, WeChat, etc. — update them to
`https://eduliuym.github.io/Lym/`.

The old URL will keep working for a long time thanks to GitHub's 301
redirect, so this is purely cosmetic.

---

## 6. Verify end-to-end

1. Visit `https://eduliuym.github.io/Lym/` — site should load.
2. Visit `https://888dddhhh.github.io/Lym/` — should 301-redirect to
   the new URL and load the same page.
3. Visit `https://github.com/eduliuym/Lym` — repo should be there.
4. Trigger the **Update Scholar Metrics** workflow once (Actions →
   *Update Scholar Metrics* → *Run workflow*) to make sure secrets
   and write access still work under the new account.

That's it. The scholar data pipeline keeps working unchanged.
