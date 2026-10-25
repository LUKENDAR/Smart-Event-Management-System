SMART EVENT MANAGEMENT AND PARTICIPANT ANALYTICS SYSTEM
Website project (Flask + SQLite + Pandas + Matplotlib)

HOW TO RUN ON WINDOWS / VS CODE
1. Extract this ZIP file.
2. Open the extracted SmartEventWebsite folder in VS Code (File > Open Folder).
3. Open Terminal > New Terminal.
4. Install the libraries:
   python -m pip install -r requirements.txt
5. Start the website:
   python app.py
6. In the terminal, look for a local address similar to http://127.0.0.1:5000
7. Hold Ctrl and click the address, or copy it into Chrome.
8. Use Add participant to enter your own data. Dashboard totals and chart update from the SQLite database.
9. Stop the website with Ctrl+C in the VS Code terminal.

IMPORTANT
- This is a local development website for a student project, not a deployed public website.
- Records are saved in event_management.db in this project folder and remain after you close the browser.
- Do not delete event_management.db if you want to keep your entered records.
- Public holidays uses the Nager.Date public API and requires internet; the rest of the website works if that API is unavailable.
- The website has Add, Read, Update, Delete, search, CSV/JSON export, API endpoints, email/phone validation, logging, and database-backed analytics.
- Do not use the Flask debug server for public production hosting.
