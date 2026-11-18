# One portal, many domains

> Internal document. Remove before the repository is made public.

## The plan

- One main domain, the `.ai` one, is the portal. Every tool lives inside it.
- Every other domain you own (the `.io`, and any others) forwards to the main one.
- Customers only ever see and remember one address. New tools are added to the portal, never to a new site.

## The main domain

**neuraldesk.ai** is the portal. It matches the brand shown on the site ("Neural Desk"). It is set once in `PORTAL.primaryDomain`
at the top of the script in `website/index.html`. Forwarding of the other domains comes later, using the steps below.

## Forward the other domains (GoDaddy)

Do this for each secondary domain, in your own GoDaddy account:

1. Open the domain, then its settings, then the Forwarding section.
2. Forward to `https://<main-domain>`.
3. Choose **permanent (301)**. Do not choose "forward with masking", it hides the real address and hurts search.
4. Add forwarding for `www` as well as the bare domain.
5. If you use email on a secondary domain, check that forwarding does not replace its mail records.

GoDaddy's screens change, so follow their current wording. Test by opening each secondary domain in a private window. It must land on the
main domain with a padlock.

## Host the portal

The portal is currently one HTML file (`website/index.html`) with sample data. To show it live you need a host. Simple options:
Netlify, Cloudflare Pages, Vercel, or GoDaddy's own hosting. For the first look, upload the `website` folder and point the main domain at it.
The host tells you the exact DNS records to add in GoDaddy (usually an A record for the bare domain and a CNAME for `www`).

The real product later needs a server (accounts, uploads, billing, the Windows helper connection), so choose a host that can grow into that.

## Adding a future tool to the portal

In `website/index.html`, add one line to the `PRODUCTS` list near the top of the script:

```
{id:"gst",icon:"G",name:"GST return checks",status:"planned",line:"One sentence on what it does."}
```

It appears on the landing page and in the app's "All tools" screen. Give it `route:"some-page"` and a view when it is ready to open.
One account, one sign in, one plan covers all of them.

## What I need from you to go further

- The exact registered names of the domains and which one is the main one.
- Where you want it hosted. If you give me access to a hosting account through a connected tool, I can deploy. I cannot register
  domains, change GoDaddy DNS or forwarding, or sign in to your accounts.
