import os
import pickle
import re
import string
from datetime import datetime
from functools import wraps
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree

import pandas as pd
import requests
from flask import Flask, request, render_template, jsonify, make_response, redirect, url_for, session, flash
from flask_mail import Mail, Message
from markupsafe import Markup, escape
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Import database and authentication
try:
    from .models import db, PredictionHistory, AdminUser, FakeNewsReport, User
    from .auth import generate_auth_token, verify_auth_token, token_required, admin_only
    from .config import config
except ImportError:
    from models import db, PredictionHistory, AdminUser, FakeNewsReport, User
    from auth import generate_auth_token, verify_auth_token, token_required, admin_only
    from config import config

def load_pickle(path, required=True):
    """Load a pickle from the project root, with clear errors for required files."""
    full_path = os.path.join(BASE_DIR, path)
    if not os.path.exists(full_path):
        if required:
            raise FileNotFoundError(f'Required model artifact missing: {path}')
        return None
    with open(full_path, 'rb') as file:
        return pickle.load(file)


# Loading the models and vectorizer
LrModel = load_pickle('LrModel.pkl')
DtModel = load_pickle('DtModel.pkl')
RFModel = load_pickle('RFModel.pkl', required=False)
GBModel = load_pickle('GBModel.pkl')
vector = load_pickle('vectorizer.pkl')
CLICKBAIT_KEYWORDS = [
    'shocking', 'you won\'t believe', 'breaking', 'viral', 'secret', 'exposed',
    'unbelievable', 'miracle', 'sensational', 'must read', 'confirmed',
    'outrage', 'exclusive', 'money', 'shocking', 'fake', 'hoax', 'urgent',
    'alert', 'scandal', 'bombshell', 'scary', 'hidden', 'sensational',
    'last chance', 'don\'t miss', 'act now', 'reveal', 'shocker'
]
SUSPICIOUS_DOMAIN_TOKENS = [
    'click', 'buzz', 'update', 'alert', 'breaking', 'truth', 'info', 'report',
    'today', 'instant', 'viral', 'latest', 'exclusive', 'news24', 'newsnow',
    'worldnews', 'daily', 'dailynews', 'headline', 'shocking'
]
TRUSTED_NEWS_DOMAINS = [
    'punchng.com',
    'punch.ng',
    'guardian.ng',
    'vanguardngr.com',
    'premiumtimesng.com',
    'channelstv.com',
    'thisdaylive.com',
    'dailytrust.com',
    'leadership.ng',
    'thenationonlineng.net',
    'tribuneonlineng.com',
    'sunnewsonline.com',
    'businessday.ng',
    'thecable.ng',
    'saharareporters.com',
    'nairametrics.com',
    'arise.tv',
    'ait.live',
    'tvcnews.tv',
    'nigerianstat.gov.ng',
    'inecnigeria.org',
    'cenbank.org',
    'ndlea.gov.ng',
    'ncdc.gov.ng',
    'who.int',
    'thesun.ng'
]
FACT_CHECK_ENDPOINT = 'https://factchecktools.googleapis.com/v1alpha1/claims:search'
WEB_SEARCH_ENDPOINT = 'https://www.googleapis.com/customsearch/v1'
PUBLIC_SEARCH_ENDPOINT = 'https://html.duckduckgo.com/html/'
GOOGLE_NEWS_RSS_ENDPOINT = 'https://news.google.com/rss/search'
TRUSTED_SOURCE_DOMAINS = TRUSTED_NEWS_DOMAINS + [
    'bbc.com',
    'bbc.co.uk',
    'reuters.com',
    'apnews.com',
    'afp.com',
    'africacheck.org',
    'businessinsider.com',
]
NEWS_SOURCE_DOMAIN_HINTS = {
    'punch newspapers': 'punchng.com',
    'punch': 'punchng.com',
    'vanguard news': 'vanguardngr.com',
    'vanguard': 'vanguardngr.com',
    'channels television': 'channelstv.com',
    'channels tv': 'channelstv.com',
    'business insider africa': 'businessinsider.com',
    'businessday': 'businessday.ng',
    'the cable': 'thecable.ng',
    'thecable': 'thecable.ng',
    'premium times': 'premiumtimesng.com',
    'guardian nigeria': 'guardian.ng',
    'daily trust': 'dailytrust.com',
    'leadership': 'leadership.ng',
}
WEB_RESULT_LIMIT = 10
TRUSTED_CORROBORATION_TARGET = 4
REPORTED_BY_TRUSTED_SOURCES_STATUS = 'Reported by trusted sources'
LEGACY_SOURCE_BACKED_STATUS = 'Source-backed'
TRUSTED_SOURCE_STATUSES = {REPORTED_BY_TRUSTED_SOURCES_STATUS, LEGACY_SOURCE_BACKED_STATUS}
STATUS_LABELS = {
    REPORTED_BY_TRUSTED_SOURCES_STATUS: 'Reported by trusted sources',
    LEGACY_SOURCE_BACKED_STATUS: 'Reported by trusted sources',
    'Real': 'Looks real',
    'Fake': 'Likely fake',
    'Unreliable': 'Needs more review',
}

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static'),
)

# Load configuration
app.config.from_object(config[os.environ.get('FLASK_ENV', 'development')])

# Initialize database
db.init_app(app)


@app.context_processor
def template_helpers():
    return {'status_label': status_label}




def get_history():
    """Get prediction history from database"""
    return PredictionHistory.query.order_by(PredictionHistory.timestamp.desc()).all()


def get_current_admin():
    token = request.cookies.get('auth_token')
    if not token:
        return None
    user_id = verify_auth_token(token)
    if not user_id:
        return None
    return AdminUser.query.filter_by(id=user_id, is_active=True).first()


def admin_page_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        admin = get_current_admin()
        if not admin:
            flash('Please sign in as an admin to continue.', 'error')
            return redirect(url_for('admin_login_page', next=request.path))
        request.admin_user = admin
        return f(*args, **kwargs)

    return decorated


def user_page_context():
    user_id = session.get('user_id')
    user = User.query.get(user_id) if user_id else None
    return {'current_user': user}


def page_auth_context():
    context = user_page_context()
    context['current_admin'] = get_current_admin()
    return context


def save_prediction(entry_data):
    """Save prediction to database"""
    prediction = PredictionHistory(
        source_type=entry_data['source_type'],
        input_text=entry_data['query'],
        analyzed_text=entry_data.get('analyzed_text'),
        status=entry_data['status'],
        confidence_score=entry_data['confidence_score'],
        domain=entry_data.get('domain'),
        risk_score=entry_data.get('risk_score'),
        matched_tokens=entry_data.get('matched_tokens'),
        clickbait_matches=entry_data.get('clickbait_matches'),
        summary=entry_data.get('summary'),
        model_results=entry_data['model_results']
    )
    try:
        db.session.add(prediction)
        db.session.commit()
        return prediction
    except Exception:
        db.session.rollback()
        app.logger.exception('Unable to save prediction history')
        return None


# Text Cleaning Function
def textCleaner(text):
    text = str(text)
    text = text.lower()
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    text = re.sub(r'<.*?>+', '', text)
    text = re.sub('[' + re.escape(string.punctuation) + ']', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\w*\d\w*', '', text)
    return text.strip()


def highlight_clickbait(text, keywords):
    escaped_text = str(escape(text))
    pattern = r'\b(' + '|'.join(re.escape(word) for word in keywords) + r')\b'
    highlighted = re.sub(pattern, r'<span class="highlight">\1</span>', escaped_text, flags=re.IGNORECASE)
    return Markup(highlighted)


def extract_title_and_text_from_url(raw_url):
    normalized_url = raw_url
    if not raw_url.startswith(('http://', 'https://')):
        normalized_url = 'http://' + raw_url
    try:
        response = requests.get(
            normalized_url,
            timeout=8,
            headers={
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
                )
            },
        )
        response.raise_for_status()
        content = response.text
        title_match = re.search(r'<title>(.*?)</title>', content, flags=re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ''
        title = re.sub(r'\s+', ' ', title)
        text = re.sub('<script.*?>.*?</script>', '', content, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub('<style.*?>.*?</style>', '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub('<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        if title:
            return f"{title}. {text[:1800]}"
        return text[:2000]
    except Exception:
        return raw_url


def analyze_domain(url):
    if not url:
        return '', [], 0
    parsed = urlparse(url if url.startswith(('http://', 'https://')) else 'http://' + url)
    domain = parsed.netloc.lower().replace('www.', '')
    found_tokens = [token for token in SUSPICIOUS_DOMAIN_TOKENS if token in domain]
    score = len(found_tokens)
    return domain, found_tokens, score


def is_known_news_domain(domain):
    return any(domain == item or domain.endswith('.' + item) for item in TRUSTED_NEWS_DOMAINS)


def extract_search_query(text, max_words=14):
    for line in str(text).splitlines():
        line = re.sub(r'\s+', ' ', line).strip()
        if 20 <= len(line) <= 180:
            words = line.split()
            return ' '.join(words[:max_words])

    cleaned = re.sub(r'\s+', ' ', str(text)).strip()
    sentence_match = re.search(r'(.{30,180}?)(?:[.!?]|$)', cleaned)
    candidate = sentence_match.group(1) if sentence_match else cleaned
    candidate = textCleaner(candidate)
    return ' '.join(candidate.split()[:max_words])


def build_fact_check_query(text):
    query = extract_search_query(text)
    if query:
        return query
    cleaned = re.sub(r'\s+', ' ', textCleaner(text)).strip()
    words = cleaned.split()
    return ' '.join(words[:14])


def chunked(items, size):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def build_web_search_queries(text, source_domain=''):
    base_query = build_fact_check_query(text)
    queries = []
    if base_query:
        queries.append(base_query)
        if source_domain:
            queries.append(f'{base_query} -site:{source_domain}')
            queries.append(f'site:{source_domain} {base_query}')

        for domains in chunked(TRUSTED_NEWS_DOMAINS, 8):
            nigerian_sites = ' OR '.join(f'site:{domain}' for domain in domains)
            queries.append(f'{base_query} Nigeria ({nigerian_sites})')

        global_sites = ' OR '.join(f'site:{domain}' for domain in TRUSTED_SOURCE_DOMAINS[-6:])
        queries.append(f'{base_query} ({global_sites})')

    unique_queries = []
    for query in queries:
        if query and query not in unique_queries:
            unique_queries.append(query)
    return unique_queries[:7]


def build_focused_trusted_queries(text, source_domain=''):
    base_query = build_fact_check_query(text)
    if not base_query:
        return []

    domains = [domain for domain in TRUSTED_NEWS_DOMAINS if domain != source_domain]
    priority_domains = domains[:18]
    return [f'site:{domain} {base_query}' for domain in priority_domains]


def google_api_error_message(exc, service_name):
    response = getattr(exc, 'response', None)
    if response is None:
        return f'{service_name} lookup failed. Please check your internet connection and try again.'
    try:
        payload = response.json()
        google_message = payload.get('error', {}).get('message')
    except ValueError:
        google_message = ''
    if response.status_code == 403:
        if google_message:
            return f'{service_name} rejected the request: {google_message}'
        return (
            f'{service_name} rejected the request. Check that the API is enabled, billing/quota is available, '
            'the key is unrestricted or allows this API, and the search engine ID is correct.'
        )
    if response.status_code == 400:
        if google_message:
            return f'{service_name} rejected the query: {google_message}'
        return f'{service_name} rejected the query. Check the API key and search configuration.'
    return f'{service_name} lookup failed with HTTP {response.status_code}.'


def search_google_fact_checks(text, language_code='en'):
    api_key = os.environ.get('GOOGLE_FACT_CHECK_API_KEY')
    if not api_key:
        return {
            'configured': False,
            'query': '',
            'matches': [],
            'error': None,
        }

    query = build_fact_check_query(text)
    if not query:
        return {
            'configured': True,
            'query': '',
            'matches': [],
            'error': 'Not enough text to search fact-check databases.',
        }

    params = {
        'key': api_key,
        'query': query,
        'languageCode': language_code,
        'pageSize': 5,
    }
    try:
        response = requests.get(FACT_CHECK_ENDPOINT, params=params, timeout=8)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        return {
            'configured': True,
            'query': query,
            'matches': [],
            'error': google_api_error_message(exc, 'Google Fact Check'),
        }

    matches = []
    for claim in data.get('claims', []):
        reviews = claim.get('claimReview', [])
        first_review = reviews[0] if reviews else {}
        publisher = first_review.get('publisher', {})
        matches.append({
            'text': claim.get('text', ''),
            'claimant': claim.get('claimant', ''),
            'claim_date': claim.get('claimDate', ''),
            'publisher': publisher.get('name', ''),
            'publisher_site': publisher.get('site', ''),
            'title': first_review.get('title', ''),
            'url': first_review.get('url', ''),
            'rating': first_review.get('textualRating', ''),
            'review_date': first_review.get('reviewDate', ''),
            'language_code': claim.get('languageCode', ''),
        })

    return {
        'configured': True,
        'query': query,
        'matches': matches,
        'error': None,
    }


def normalize_search_result(item):
    link = item.get('link', '')
    domain = urlparse(link).netloc.lower().replace('www.', '')
    return {
        'title': item.get('title', ''),
        'link': link,
        'snippet': item.get('snippet', ''),
        'domain': domain,
        'trusted': is_trusted_source_domain(domain),
        'source_type': item.get('source_type', 'search_result'),
    }


class PublicSearchParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self.current = None
        self.capture = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        class_names = attrs.get('class', '')
        if tag == 'a' and 'result__a' in class_names:
            self.current = {'title': '', 'link': self.clean_link(attrs.get('href', '')), 'snippet': ''}
            self.capture = 'title'
        elif self.current and tag == 'a' and 'result__snippet' in class_names:
            self.capture = 'snippet'

    def handle_data(self, data):
        if self.current and self.capture:
            self.current[self.capture] += data

    def handle_endtag(self, tag):
        if self.current and self.capture and tag == 'a':
            if self.capture == 'title':
                self.results.append(self.current)
                self.current = None
            self.capture = None

    @staticmethod
    def clean_link(link):
        if not link:
            return ''
        parsed = urlparse(link)
        query_values = parse_qs(parsed.query)
        if 'uddg' in query_values:
            return unquote(query_values['uddg'][0])
        return link


def search_public_web(query, timeout=8):
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
        )
    }
    response = requests.get(
        PUBLIC_SEARCH_ENDPOINT,
        params={'q': query, 'kl': 'ng-en'},
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    parser = PublicSearchParser()
    parser.feed(response.text)
    return [normalize_search_result(item) for item in parser.results]


def source_name_to_domain(source_name, source_url=''):
    if source_url:
        domain = urlparse(source_url).netloc.lower().replace('www.', '')
        if domain:
            return domain

    normalized_name = re.sub(r'\s+', ' ', str(source_name or '').lower()).strip()
    for source_hint, domain in NEWS_SOURCE_DOMAIN_HINTS.items():
        if source_hint in normalized_name:
            return domain
    return normalized_name.replace(' ', '') if normalized_name else ''


def search_google_news_sources(query, timeout=8):
    response = requests.get(
        GOOGLE_NEWS_RSS_ENDPOINT,
        params={'q': query, 'hl': 'en-NG', 'gl': 'NG', 'ceid': 'NG:en'},
        headers={
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
            )
        },
        timeout=timeout,
    )
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    results = []
    for item in root.findall('.//item'):
        title = item.findtext('title', default='')
        link = item.findtext('link', default='')
        description = re.sub(r'<[^>]+>', ' ', item.findtext('description', default=''))
        description = re.sub(r'\s+', ' ', description).strip()
        source = item.find('source')
        source_name = source.text if source is not None else ''
        source_url = source.attrib.get('url', '') if source is not None else ''
        domain = source_name_to_domain(source_name, source_url)
        results.append({
            'title': title,
            'link': link,
            'snippet': description or f'Google News result from {source_name}',
            'domain': domain,
            'trusted': is_trusted_source_domain(domain),
            'source_type': 'google_news',
        })
    return results


def append_unique_results(results, seen_links, incoming):
    for result in incoming:
        if len(results) >= WEB_RESULT_LIMIT:
            break
        if result['link'] and result['link'] not in seen_links:
            seen_links.add(result['link'])
            results.append(result)


def has_corroborating_trusted_match(results):
    return any(
        result['trusted'] and result.get('source_type') != 'submitted_url'
        for result in results
    )


def corroborating_trusted_count(results):
    return sum(
        1 for result in results
        if result['trusted'] and result.get('source_type') != 'submitted_url'
    )


def source_url_result(source_url, source_domain):
    if not source_url or not source_domain or not is_trusted_source_domain(source_domain):
        return None
    return {
        'title': 'Submitted source article from trusted domain',
        'link': source_url,
        'snippet': 'The submitted URL is from a trusted publisher domain in the source list.',
        'domain': source_domain,
        'trusted': True,
        'source_type': 'submitted_url',
    }


def search_web_sources(text, source_domain='', source_url=''):
    api_key = os.environ.get('GOOGLE_SEARCH_API_KEY')
    search_engine_id = os.environ.get('GOOGLE_SEARCH_ENGINE_ID')

    queries = build_web_search_queries(text, source_domain)
    focused_queries = build_focused_trusted_queries(text, source_domain)
    if not queries:
        return {
            'configured': True,
            'query': '',
            'queries': [],
            'focused_queries': [],
            'results': [],
            'trusted_matches': [],
            'unknown_matches': [],
            'error': 'Not enough text to search the web.',
        }

    results = []
    seen_links = set()
    errors = []
    submitted_source = source_url_result(source_url, source_domain)

    google_search_available = bool(api_key and search_engine_id)
    if google_search_available:
        try:
            for query in queries:
                params = {
                    'key': api_key,
                    'cx': search_engine_id,
                    'q': query,
                    'num': 8,
                }
                response = requests.get(WEB_SEARCH_ENDPOINT, params=params, timeout=8)
                response.raise_for_status()
                data = response.json()
                append_unique_results(
                    results,
                    seen_links,
                    [normalize_search_result(item) for item in data.get('items', [])],
                )
                if len(results) >= WEB_RESULT_LIMIT and has_corroborating_trusted_match(results):
                    break
        except requests.RequestException as exc:
            errors.append(google_api_error_message(exc, 'Web search'))

    if len(results) < WEB_RESULT_LIMIT or not has_corroborating_trusted_match(results):
        for query in queries[:2]:
            try:
                append_unique_results(results, seen_links, search_public_web(query, timeout=5))
            except requests.RequestException as exc:
                errors.append(f'Public web fallback failed: {google_api_error_message(exc, "Public web search")}')
            if len(results) >= WEB_RESULT_LIMIT and has_corroborating_trusted_match(results):
                break

    if (
        corroborating_trusted_count(results) < TRUSTED_CORROBORATION_TARGET
        and len(results) < WEB_RESULT_LIMIT
    ):
        for query in queries[:1]:
            try:
                append_unique_results(results, seen_links, search_google_news_sources(query, timeout=4))
            except requests.RequestException as exc:
                errors.append(f'Google News fallback failed: {google_api_error_message(exc, "Google News search")}')
            except ElementTree.ParseError:
                errors.append('Google News fallback failed: unable to parse news results.')
            if (
                corroborating_trusted_count(results) >= TRUSTED_CORROBORATION_TARGET
                or len(results) >= WEB_RESULT_LIMIT
            ):
                break

    if (
        corroborating_trusted_count(results) < TRUSTED_CORROBORATION_TARGET
        and len(results) < WEB_RESULT_LIMIT
    ):
        for query in focused_queries[:4]:
            try:
                append_unique_results(results, seen_links, search_public_web(query, timeout=4))
            except requests.RequestException as exc:
                errors.append(f'Trusted-domain fallback failed: {google_api_error_message(exc, "Trusted-domain search")}')
            if (
                corroborating_trusted_count(results) >= TRUSTED_CORROBORATION_TARGET
                or len(results) >= WEB_RESULT_LIMIT
            ):
                break

    if submitted_source:
        append_unique_results(results, seen_links, [submitted_source])

    trusted_matches = [result for result in results if result['trusted']]
    unknown_matches = [result for result in results if not result['trusted']]
    error = None
    if not results and errors:
        error = errors[0]
    elif results and errors:
        error = 'Google Custom Search was unavailable, so public web fallback results are shown.'
    return {
        'configured': True,
        'query': queries[0],
        'queries': queries,
        'focused_queries': focused_queries,
        'results': results,
        'trusted_matches': trusted_matches,
        'unknown_matches': unknown_matches,
        'error': error,
    }


def is_trusted_source_domain(domain):
    return any(domain == item or domain.endswith('.' + item) for item in TRUSTED_SOURCE_DOMAINS)


def empty_fact_check_state():
    return {'configured': False, 'query': '', 'matches': [], 'error': None}


def empty_web_verification_state():
    return {
        'configured': False,
        'query': '',
        'queries': [],
        'focused_queries': [],
        'results': [],
        'trusted_matches': [],
        'unknown_matches': [],
        'error': None,
    }


def average(values):
    return sum(values) / len(values) if values else 0.0


def status_label(status):
    return STATUS_LABELS.get(status, status)


def is_trusted_source_status(status):
    return status in TRUSTED_SOURCE_STATUSES


def classify_fact_check_rating(rating):
    rating_text = str(rating or '').lower()
    if any(term in rating_text for term in ['false', 'not true', 'barely true', 'fake', 'hoax', 'scam', 'fabricated']):
        return 'Fake'
    if any(term in rating_text for term in ['misleading', 'partly true', 'half true', 'mixture', 'mixed']):
        return 'Unreliable'
    if any(term in rating_text for term in ['true', 'correct', 'accurate']):
        return 'Real'
    return None


def external_fact_check_signal(fact_check):
    for match in fact_check.get('matches', []):
        signal = classify_fact_check_rating(match.get('rating'))
        if signal:
            return signal, match.get('publisher') or match.get('publisher_site') or 'Google Fact Check'
    return None, ''


def apply_evidence_adjustment(model_status, confidence_score, avg_true, avg_fake, fact_check, web_verification, source_domain='', source_type='text'):
    fact_signal, fact_source = external_fact_check_signal(fact_check)
    trusted_matches = web_verification.get('trusted_matches', [])
    trusted_count = len(trusted_matches)
    corroborating_count = sum(1 for result in trusted_matches if result.get('source_type') != 'submitted_url')
    known_source_domain = bool(source_domain and is_known_news_domain(source_domain))
    enough_typed_text_sources = source_type == 'text' and corroborating_count >= 2
    enough_url_sources = source_type == 'url' and trusted_count >= 1

    if fact_signal:
        note = f'A reviewed fact-check from {fact_source} was found, so the final result was updated.'
        if fact_signal == 'Unreliable':
            return 'Unreliable', min(confidence_score, 65), note
        return fact_signal, max(confidence_score, 75), note

    if model_status != 'Fake' and (enough_typed_text_sources or enough_url_sources):
        return (
            REPORTED_BY_TRUSTED_SOURCES_STATUS,
            max(confidence_score, 70),
            f'The story was found on trusted sources ({trusted_count} match(es)), so the final result uses those sources first.',
        )

    if model_status == 'Fake' and (enough_typed_text_sources or enough_url_sources):
        return (
            REPORTED_BY_TRUSTED_SOURCES_STATUS,
            70,
            (
                f'The computer model thought the text looked suspicious, but trusted sources also reported it '
                f'({trusted_count} match(es)). The final result follows the trusted sources.'
            ),
        )

    if model_status == 'Fake' and known_source_domain:
        return (
            REPORTED_BY_TRUSTED_SOURCES_STATUS,
            65,
            (
                f'The computer model thought the text looked suspicious, but the submitted link is from '
                f'a trusted publisher ({source_domain}).'
            ),
        )

    if model_status == 'Fake':
        return (
            'Unreliable',
            min(confidence_score, 55),
            'The computer model thought the text looked suspicious, but no trusted source or fact-check proved it is fake.',
        )

    return model_status, confidence_score, None


def is_url(value):
    return str(value).strip().startswith(('http://', 'https://'))


def summarize_history_text(entry, limit=320):
    text = entry.summary or entry.analyzed_text or entry.input_text or ''
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(' ', 1)[0] + '...'


def history_article_title(entry):
    text = re.sub(r'\s+', ' ', (entry.input_text or entry.summary or '')).strip()
    if is_url(text):
        return entry.domain or text
    title = text[:120].strip()
    return title + ('...' if len(text) > 120 else '')


def history_to_article(entry):
    return {
        'id': entry.id,
        'title': history_article_title(entry),
        'content': summarize_history_text(entry),
        'pubDate': entry.timestamp.strftime('%Y-%m-%d %H:%M UTC'),
        'creator': entry.domain or entry.source_type.title(),
        'link': entry.input_text if is_url(entry.input_text) else url_for('prediction_detail', prediction_id=entry.id),
        'detail_link': url_for('prediction_detail', prediction_id=entry.id),
        'status': entry.status,
        'confidence_score': entry.confidence_score,
    }


def history_articles_by_status(status, limit=20):
    statuses = status if isinstance(status, (list, tuple, set)) else [status]
    entries = (
        PredictionHistory.query
        .filter(PredictionHistory.status.in_(statuses))
        .order_by(PredictionHistory.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [history_to_article(entry) for entry in entries]


def build_model_results(X):
    models = [
        ('Logistic Regression', LrModel),
        ('Decision Tree', DtModel),
        ('Gradient Boosting', GBModel),
        ('Random Forest', RFModel),
    ]
    models = [(model_name, model) for model_name, model in models if model is not None]
    model_results = []
    true_votes = 0
    fake_votes = 0
    true_probs = []
    fake_probs = []
    for model_name, model in models:
        try:
            proba = model.predict_proba(X)[0]
        except Exception:
            pred_val = int(model.predict(X)[0])
            proba = [1.0 - pred_val, pred_val]
        pred = int(model.predict(X)[0])
        fake_votes += int(pred == 0)
        true_votes += int(pred == 1)
        true_probs.append(float(proba[1]))
        fake_probs.append(float(proba[0]))
        model_results.append({
            'name': model_name,
            'label': 'Looks real' if pred == 1 else 'Looks suspicious',
            'true_probability': round(float(proba[1]) * 100, 1),
            'fake_probability': round(float(proba[0]) * 100, 1),
        })
    return model_results, true_votes, fake_votes, average(true_probs), average(fake_probs)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/home')
def home():
    return render_template('home.html', **page_auth_context())


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not username or not email or not password:
            flash('Username, email, and password are required.', 'error')
            return render_template('register.html')
        if User.query.filter_by(username=username).first():
            flash('That username is already taken.', 'error')
            return render_template('register.html')
        if User.query.filter_by(email=email).first():
            flash('That email is already registered.', 'error')
            return render_template('register.html')

        user = User(username=username, email=email, is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user.id
        flash('Account created. You are signed in.', 'success')
        response = make_response(redirect(url_for('home')))
        response.delete_cookie('auth_token')
        return response

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'POST':
        username_or_email = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email.lower())
        ).first()

        if not user or not user.is_active or not user.check_password(password):
            flash('Invalid user login details.', 'error')
            return render_template('user_login.html')

        user.last_login = datetime.utcnow()
        db.session.commit()
        session['user_id'] = user.id
        flash('Welcome back.', 'success')
        response = make_response(redirect(url_for('home')))
        response.delete_cookie('auth_token')
        return response

    return render_template('user_login.html')


@app.route('/logout', methods=['POST'])
def user_logout():
    session.pop('user_id', None)
    flash('You have been signed out.', 'success')
    return redirect(url_for('home'))


@app.route('/predict', methods=['POST'])
def predict():
    article_text = request.form.get('article', '').strip()
    news_url = request.form.get('news_url', '').strip()
    if not article_text and not news_url:
        return render_template(
            'result.html',
            status='Unreliable',
            confidence_score=0,
            warnings=['Please paste news text or a URL before running verification.'],
            highlighted_text='No article text was provided.',
            domain='',
            risk_score=0,
            model_results=[],
            source_type='text',
            raw_input='',
            clickbait_matches=[],
            fact_check=empty_fact_check_state(),
            web_verification=empty_web_verification_state(),
            **page_auth_context(),
        ), 400

    source_type = 'url' if news_url else 'text'
    raw_input = article_text or news_url

    if article_text and news_url:
        url_text = extract_title_and_text_from_url(news_url)
        analyzed_text = f'{article_text}\n\nURL page context:\n{url_text}'
    elif source_type == 'url':
        analyzed_text = extract_title_and_text_from_url(news_url)
    else:
        analyzed_text = article_text

    domain, matched_tokens, risk_score = analyze_domain(news_url)
    cleaned_text = textCleaner(analyzed_text)
    warnings = []
    model_results = []
    avg_true = 0.0
    avg_fake = 0.0

    weak_url_extraction = bool(news_url) and not article_text and len(cleaned_text.split()) < 25
    if weak_url_extraction:
        status = 'Unreliable'
        confidence_score = 0
        warnings.append(
            'The app could not extract enough article text from this URL, so it is not making a fake/real model verdict.'
        )
    else:
        new_def_test = pd.DataFrame({'text': [cleaned_text]})
        new_xv_test = vector.transform(new_def_test['text'])
        model_results, true_votes, fake_votes, avg_true, avg_fake = build_model_results(new_xv_test)
        if true_votes > fake_votes:
            status = 'Real'
        elif true_votes == fake_votes:
            status = 'Unreliable'
        else:
            status = 'Fake'
        if status == 'Real':
            confidence_score = round(avg_true * 100, 1)
        elif status == 'Fake':
            confidence_score = round(avg_fake * 100, 1)
        else:
            confidence_score = round(max(avg_true, avg_fake) * 100, 1)

    if risk_score > 0:
        warnings.append(f'Watch out: this domain contains suspicious tokens: {", ".join(matched_tokens)}')
    if domain and is_known_news_domain(domain):
        warnings.append('This link is from a known news publisher. Check the source results before trusting the computer model.')
    if status == 'Fake':
        warnings.append('The computer model thinks the text looks suspicious. This is not the same as a fact-check verdict.')
    if source_type == 'url' and not matched_tokens:
        warnings.append('Domain appears normal but content should still be reviewed carefully.')

    fact_check = search_google_fact_checks(analyzed_text)
    if fact_check['configured'] and fact_check['matches']:
        warnings.append('Google Fact Check found related reviewed claims. Compare the ratings below with the article context.')
    elif fact_check['configured'] and not fact_check['error']:
        warnings.append('No related Google Fact Check matches were found for this input.')

    web_verification = search_web_sources(analyzed_text, domain, news_url)
    if web_verification['configured'] and web_verification['trusted_matches']:
        warnings.append(
            f'The source check found {len(web_verification["trusted_matches"])} trusted news/source match(es). Compare the links below.'
        )
    elif web_verification['configured'] and web_verification['results'] and not web_verification['trusted_matches']:
        warnings.append('Web search found results, but none came from the trusted source list.')
    elif web_verification['configured'] and not web_verification['error']:
        warnings.append('Web search returned no matching source results for this input.')
    if source_type == 'text' and len(web_verification.get('trusted_matches', [])) == 1:
        warnings.append(
            'Only one trusted-source search result was found for this typed text, so the app does not treat it as confirmed by trusted sources.'
        )

    adjusted_status, adjusted_confidence, adjustment_note = apply_evidence_adjustment(
        status,
        confidence_score,
        avg_true,
        avg_fake,
        fact_check,
        web_verification,
        domain,
        source_type,
    )
    if adjustment_note:
        warnings.append(adjustment_note)
        status = adjusted_status
        confidence_score = adjusted_confidence

    clickbait_matches = [word for word in CLICKBAIT_KEYWORDS if re.search(r'\b' + re.escape(word) + r'\b', analyzed_text, re.IGNORECASE)]
    highlighted_text = highlight_clickbait(analyzed_text[:2500], clickbait_matches or CLICKBAIT_KEYWORDS)

    entry = {
        'source_type': source_type,
        'query': raw_input,
        'analyzed_text': analyzed_text[:2500],
        'status': status,
        'confidence_score': confidence_score,
        'domain': domain,
        'risk_score': risk_score,
        'matched_tokens': matched_tokens,
        'clickbait_matches': clickbait_matches,
        'summary': analyzed_text[:500],
        'model_results': model_results,
    }
    
    # Save to database
    save_prediction(entry)

    return render_template(
        'result.html',
        status=status,
        confidence_score=confidence_score,
        warnings=warnings,
        highlighted_text=highlighted_text,
        domain=domain,
        risk_score=risk_score,
        model_results=model_results,
        source_type=source_type,
        raw_input=raw_input,
        clickbait_matches=clickbait_matches,
        fact_check=fact_check,
        web_verification=web_verification,
        **page_auth_context(),
    )


@app.route('/dashboard')
def dashboard():
    history = get_history()
    total_checks = len(history)
    total_fake = sum(1 for entry in history if entry.status == 'Fake')
    total_real = sum(1 for entry in history if entry.status == 'Real')
    total_source_backed = sum(1 for entry in history if is_trusted_source_status(entry.status))
    total_unreliable = sum(1 for entry in history if entry.status == 'Unreliable')
    avg_confidence = round(average([entry.confidence_score for entry in history]), 1) if history else 0.0
    return render_template(
        'dashboard.html',
        history=history[:5],
        total_checks=total_checks,
        total_fake=total_fake,
        total_real=total_real,
        total_source_backed=total_source_backed,
        total_unreliable=total_unreliable,
        avg_confidence=avg_confidence,
        **page_auth_context(),
    )


@app.route('/history')
def history_view():
    history = get_history()
    return render_template(
        'history.html',
        history=history,
        **page_auth_context(),
    )


@app.route('/history/<int:prediction_id>')
def prediction_detail(prediction_id):
    prediction = PredictionHistory.query.get_or_404(prediction_id)
    highlighted_text = highlight_clickbait(
        prediction.analyzed_text or prediction.summary or prediction.input_text,
        prediction.clickbait_matches or CLICKBAIT_KEYWORDS,
    )
    return render_template(
        'result.html',
        status=prediction.status,
        confidence_score=prediction.confidence_score,
        warnings=['This is a stored result preview from verification history.'],
        highlighted_text=highlighted_text,
        domain=prediction.domain or '',
        risk_score=prediction.risk_score or 0,
        model_results=prediction.model_results or [],
        source_type=prediction.source_type,
        raw_input=prediction.input_text,
        clickbait_matches=prediction.clickbait_matches or [],
        fact_check=empty_fact_check_state(),
        web_verification=empty_web_verification_state(),
        is_stored_preview=True,
        **page_auth_context(),
    )


@app.route('/admin')
@admin_page_required
def admin():
    history = get_history()
    latest = history[0] if history else None
    regular_users = User.query.order_by(User.created_at.desc()).all()
    total_reports = FakeNewsReport.query.count()
    pending_reports = FakeNewsReport.query.filter_by(status='pending').count()
    return render_template(
        'admin.html',
        history=history[:8],
        latest=latest,
        admin_user=request.admin_user,
        regular_users=regular_users,
        total_checks=len(history),
        total_reports=total_reports,
        pending_reports=pending_reports,
    )


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login_page():
    if get_current_admin():
        return redirect(url_for('admin'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        admin_user = AdminUser.query.filter_by(username=username, is_active=True).first()
        if not admin_user or not admin_user.check_password(password):
            flash('Invalid admin login details.', 'error')
            return render_template('admin_login.html')

        token = generate_auth_token(admin_user.id)
        next_url = request.args.get('next') or url_for('admin')
        session.pop('user_id', None)
        response = make_response(redirect(next_url))
        response.set_cookie(
            'auth_token',
            token,
            httponly=True,
            secure=app.config.get('SESSION_COOKIE_SECURE', False),
            samesite='Strict',
        )
        return response

    return render_template('admin_login.html')


@app.route('/admin/logout', methods=['POST'])
def admin_logout_page():
    response = make_response(redirect(url_for('admin_login_page')))
    response.delete_cookie('auth_token')
    flash('Admin session ended.', 'success')
    return response


@app.route('/admin/users', methods=['POST'])
@admin_page_required
def admin_create_user_form():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')

    if not username or not email or not password:
        flash('Username, email, and password are required.', 'error')
        return redirect(url_for('admin'))
    if User.query.filter_by(username=username).first():
        flash('Username already exists.', 'error')
        return redirect(url_for('admin'))
    if User.query.filter_by(email=email).first():
        flash('Email already exists.', 'error')
        return redirect(url_for('admin'))

    user = User(
        username=username,
        email=email,
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash('User record created.', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/users/<int:user_id>/update', methods=['POST'])
@admin_page_required
def admin_update_user_form(user_id):
    user = User.query.get_or_404(user_id)
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')

    if not username or not email:
        flash('Username and email are required.', 'error')
        return redirect(url_for('admin'))

    username_owner = User.query.filter_by(username=username).first()
    email_owner = User.query.filter_by(email=email).first()
    if username_owner and username_owner.id != user.id:
        flash('Username already belongs to another user.', 'error')
        return redirect(url_for('admin'))
    if email_owner and email_owner.id != user.id:
        flash('Email already belongs to another user.', 'error')
        return redirect(url_for('admin'))

    user.username = username
    user.email = email
    user.is_active = request.form.get('is_active') == 'on'
    if password:
        user.set_password(password)
    db.session.commit()
    flash('User record updated.', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_page_required
def admin_delete_user_form(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('User record deleted.', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/history/<int:prediction_id>/delete', methods=['POST'])
@admin_page_required
def admin_delete_prediction_form(prediction_id):
    prediction = PredictionHistory.query.get_or_404(prediction_id)
    db.session.delete(prediction)
    db.session.commit()
    flash('History record deleted.', 'success')
    return redirect(request.referrer or url_for('admin'))


# ==================== ADMIN API ROUTES ====================

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    """Authenticate admin user and return JWT token"""
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    admin = AdminUser.query.filter_by(username=username, is_active=True).first()
    if not admin or not admin.check_password(password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    token = generate_auth_token(admin.id)
    response = make_response(jsonify({
        'token': token,
        'user': admin.to_dict()
    }))
    response.set_cookie(
        'auth_token',
        token,
        httponly=True,
        secure=app.config.get('SESSION_COOKIE_SECURE', False),
        samesite='Strict',
    )
    return response, 200


@app.route('/api/admin/logout', methods=['POST'])
@token_required
def admin_logout():
    """Logout admin user"""
    response = make_response(jsonify({'message': 'Logged out successfully'}))
    response.delete_cookie('auth_token')
    return response, 200


@app.route('/api/admin/verify-token', methods=['GET'])
@token_required
def verify_token():
    """Verify if current token is valid"""
    return jsonify({
        'valid': True,
        'user': request.admin_user.to_dict()
    }), 200


@app.route('/api/admin/stats', methods=['GET'])
@token_required
def admin_stats():
    """Get dashboard statistics"""
    history = get_history()
    
    stats = {
        'total_checks': len(history),
        'total_fake': sum(1 for h in history if h.status == 'Fake'),
        'total_real': sum(1 for h in history if h.status == 'Real'),
        'total_source_backed': sum(1 for h in history if is_trusted_source_status(h.status)),
        'total_unreliable': sum(1 for h in history if h.status == 'Unreliable'),
        'avg_confidence': round(average([h.confidence_score for h in history]), 1) if history else 0.0,
        'recent_predictions': [h.to_dict() for h in history[:10]]
    }
    return jsonify(stats), 200


@app.route('/api/admin/predictions', methods=['GET'])
@token_required
def admin_predictions():
    """Get paginated predictions"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    pagination = PredictionHistory.query.order_by(PredictionHistory.timestamp.desc()).paginate(
        page=page,
        per_page=per_page
    )
    
    return jsonify({
        'data': [p.to_dict() for p in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    }), 200


@app.route('/api/admin/predictions/<int:pred_id>', methods=['GET'])
@token_required
def get_prediction(pred_id):
    """Get a specific prediction"""
    prediction = PredictionHistory.query.get(pred_id)
    if not prediction:
        return jsonify({'error': 'Prediction not found'}), 404
    
    return jsonify(prediction.to_dict()), 200


@app.route('/api/admin/predictions/<int:pred_id>', methods=['DELETE'])
@token_required
def delete_prediction(pred_id):
    """Delete a prediction."""
    prediction = PredictionHistory.query.get(pred_id)
    if not prediction:
        return jsonify({'error': 'Prediction not found'}), 404
    
    db.session.delete(prediction)
    db.session.commit()
    return jsonify({'message': 'Prediction deleted'}), 200


@app.route('/api/admin/reports', methods=['GET'])
@token_required
def admin_reports():
    """Get fake news reports"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', None)
    
    query = FakeNewsReport.query
    if status:
        query = query.filter_by(status=status)
    
    pagination = query.order_by(FakeNewsReport.timestamp.desc()).paginate(
        page=page,
        per_page=20
    )
    
    return jsonify({
        'data': [r.to_dict() for r in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages
    }), 200


@app.route('/api/admin/reports/<int:report_id>', methods=['PUT'])
@token_required
@admin_only
def update_report(report_id):
    """Update a fake news report"""
    report = FakeNewsReport.query.get(report_id)
    if not report:
        return jsonify({'error': 'Report not found'}), 404
    
    data = request.get_json()
    report.status = data.get('status', report.status)
    report.admin_notes = data.get('admin_notes', report.admin_notes)
    
    db.session.commit()
    return jsonify(report.to_dict()), 200


@app.route('/api/admin/users', methods=['GET'])
@token_required
def admin_users():
    """Get all regular users."""
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([u.to_dict() for u in users]), 200


@app.route('/api/admin/users', methods=['POST'])
@token_required
def create_admin_user():
    """Create a regular user."""
    data = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'error': 'Username, email, and password required'}), 400
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400
    
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400
    
    user = User(
        username=username,
        email=email,
        is_active=True,
    )
    user.set_password(password)
    
    db.session.add(user)
    db.session.commit()
    
    return jsonify(user.to_dict()), 201


@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@token_required
def update_admin_user(user_id):
    """Update a regular user."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json(silent=True) or {}
    username = data.get('username', user.username).strip()
    email = data.get('email', user.email).strip().lower()

    username_owner = User.query.filter_by(username=username).first()
    email_owner = User.query.filter_by(email=email).first()
    if username_owner and username_owner.id != user.id:
        return jsonify({'error': 'Username already exists'}), 400
    if email_owner and email_owner.id != user.id:
        return jsonify({'error': 'Email already exists'}), 400

    user.username = username
    user.email = email
    user.is_active = data.get('is_active', user.is_active)
    
    if data.get('password'):
        user.set_password(data['password'])
    
    db.session.commit()
    return jsonify(user.to_dict()), 200


@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@token_required
def delete_admin_user(user_id):
    """Delete a regular user."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted'}), 200


# Authentic News page
@app.route('/news')
def news():
    articles = history_articles_by_status(['Real', *TRUSTED_SOURCE_STATUSES])
    return render_template('authenticNews.html', articles=articles, **page_auth_context())


# Report page
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '587'))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])
REPORT_RECIPIENT = os.environ.get('REPORT_RECIPIENT', app.config['MAIL_USERNAME'])
mail = Mail(app)


@app.route('/submit', methods=['POST'])
def submit():
    title = request.form['title']
    source = request.form['source']
    date = request.form['date']
    description = request.form['description']
    proof = request.form['proof']

    report = FakeNewsReport(
        article_title=title,
        article_url=source,
        reason=f'Date: {date}\nDescription: {description}\nProof: {proof}',
    )
    try:
        db.session.add(report)
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception('Unable to save fake news report')

    if app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD'] and REPORT_RECIPIENT:
        msg = Message('Report', recipients=[REPORT_RECIPIENT])
        msg.body = f'Title: {title}\nSource: {source}\nDate: {date}\nDescription: {description}\nProof: {proof}'
        mail.send(msg)
    return render_template('mailResponse.html')


@app.route('/report')
def report():
    return render_template('report.html')


@app.route('/recentFake')
def recentFake():
    articles = history_articles_by_status('Fake')
    return render_template('recentFake.html', articles=articles, **page_auth_context())


@app.route('/about')
def about():
    return render_template('about.html')


if __name__ == '__main__':
    app.run(debug=True)
