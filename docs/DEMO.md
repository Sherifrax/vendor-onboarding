# Phase 7 dashboard demo

1. Run `make up`, then start the dashboard with `cd frontend && npm run dev`.
2. Open `http://127.0.0.1:5173` and sign in with the value of `ADMIN_TOKEN` (the local Compose default is `change-me`).
3. Choose **Submit**, select **sample**, and run onboarding intake.
4. Open the new request from **Requests**. Confirm its four clearances, audit timeline, and outbox entries. The sample has 60-day terms and USD 150,000 spend, so it requires manager approval.
5. Use **Open action link** on the manager-decision outbox entry. Choose **Approve** in the signed form.
6. The request correctly waits for its required vendor documents after manager approval. Use the document-request action link to upload the required PDF/PNG/JPEG files, then use the document-review action link and choose **Accept all**.
7. Return to **Requests** (the list refreshes every five seconds). Confirm the vendor is created, then verify the record in **Vendors** and its events in **Audit**.

The dashboard is an operations view. Compliance decisions remain explicitly `SIMULATED`, and live external credentials are not required for this demonstration.
