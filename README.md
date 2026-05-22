# FakeNews Detector Web App

This is a web application called FakeNews, which is designed to detect and classify fake news articles. The app is built using Flask, a Python web framework, and utilizes a machine learning model trained on four different algorithms to achieve an accuracy of approximately 94%. The model uses four features to classify news articles as either real or fake.

## Installation

To run the FakeNews web app locally, follow these steps:

1. Clone the repository:
   ```bash
   git clone <repository_url>
   ```

2. Navigate to the project directory:
   ```bash
   cd FakeNewsDetector
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Initialize the local database:
   ```bash
   python -m FakeNews.db_init
   ```

5. Run the Flask development server:
   ```bash
   flask --app FakeNews.app run
   ```

6. Open your web browser and access the app at `http://localhost:5000`.

By default, development uses a local SQLite database. Set `DATABASE_URL` to a
MySQL connection string for production storage.

## Local Test URLs

- Check news: `http://127.0.0.1:5000/home`
- User registration: `http://127.0.0.1:5000/register`
- User login: `http://127.0.0.1:5000/login`
- Admin login: `http://127.0.0.1:5000/admin/login`
- Protected admin dashboard: `http://127.0.0.1:5000/admin`

The database initializer creates a default super admin if one does not already
exist:

```text
Username: admin
Password: admin123
```

## Google Fact Check

To enable related fact-check matches on the result page, create a Google Cloud
API key with the Fact Check Tools API enabled, then add it to `.env`:

```env
GOOGLE_FACT_CHECK_API_KEY=your-google-fact-check-api-key
```

The app uses Google Fact Check Tools `claims:search` as an evidence layer. It
does not replace the computer model and it does not prove a claim true when no
match is found.

## Internet Source Verification

Web source verification can use Google Programmable Search when it is
configured. Create a Google Programmable Search Engine and a Custom Search JSON
API key, then add both values to `.env`:

```env
GOOGLE_SEARCH_API_KEY=your-google-custom-search-api-key
GOOGLE_SEARCH_ENGINE_ID=your-programmable-search-engine-id
```

If Google returns `This project does not have the access to Custom Search JSON
API`, open Google Cloud Console for the same project that owns
`GOOGLE_SEARCH_API_KEY`, enable **Custom Search JSON API**, confirm the key is
allowed to call that API, and make sure the Programmable Search Engine is set to
search the entire web or the domains you want to verify.

If Google Custom Search is rejected or unavailable, the app falls back to a
Google News RSS lookup and public web search so the result page can still show
source evidence. The app marks matches from the trusted source list, including
Nigerian publishers and public sources such as Punch, Guardian Nigeria, Premium
Times, Channels TV, Vanguard, Daily Trust, Leadership, The Cable, BusinessDay,
Nigerian Tribune, NBS, INEC, CBN, NCDC, and WHO.

Final result labels are written in simple language. The app shows
`Reported by trusted sources` when trusted publishers report the same story,
`Needs more review` when the computer model is not enough, and `Likely fake`
only when stronger outside evidence supports that result.

## Project Structure

The project has the following structure:

- `static/`: This directory contains static files such as CSS stylesheets and client-side JavaScript files.
- `templates/`: This directory contains the HTML templates used by the Flask app for rendering the web pages.
- `DtModel.pkl`: A machine learning model file trained on the Decision Tree algorithm.
- `GBModel.pkl`: A machine learning model file trained on the Gradient Boosting algorithm.
- `LrModel.pkl`: A machine learning model file trained on the Logistic Regression algorithm.
- `vectorizer.pkl`: A pickle file containing the trained TF-IDF vectorizer used for text preprocessing.
- `Fake_new_detection.ipynb`: Jupyter Notebook file containing the code for training the machine learning models and performing analysis.
- `LICENSE`: The license file for the project.
- `README.md`: This file, providing information about the FakeNews web app.

## Usage

The FakeNews web app offers the following functionalities:

- **Check Latest News**: View the latest news articles and their classification as real or fake.
- **Check Fake News**: Enter a news article URL or text to check if it is real or fake.
- **Check Recent Fake News**: View the most recently detected fake news articles.
- **Report Fake News**: Report any suspicious news articles that you believe are fake.

## Contributing

Contributions to the FakeNews web app are welcome. If you find any bugs or have suggestions for improvements, please open an issue or submit a pull request.

## License

This project is licensed under the [MIT License](LICENSE).

Feel free to use, modify, and distribute the code for personal or commercial purposes.

## Acknowledgments

The FakeNews web app and machine learning models were developed by Hare Krishna.
