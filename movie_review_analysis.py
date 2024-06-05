import os, re
from flask import Flask, render_template, request, send_from_directory
from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired
import requests
from bs4 import BeautifulSoup
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException
from nltk.sentiment import SentimentIntensityAnalyzer
from wordcloud import WordCloud
from sklearn.metrics import precision_score, recall_score, f1_score
from collections import Counter
import matplotlib.pyplot as plt

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret'

RESULTS_DIR = "results"

def scrape_reviews(movie_title):
    query = f"{movie_title} movie reviews"
    url = f"https://www.google.com/search?q={query}"
    print(url)
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print("Error:", e)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    review_snippets = set() 
    for snippet in soup.find_all("div", class_="BNeawe s3v9rd AP7Wnd"):
        review_snippets.add(snippet.text.strip())
    return list(review_snippets)

def analyze_sentiment(reviews):
    sia = SentimentIntensityAnalyzer()
    sentiments = []
    for review in reviews:
        score = sia.polarity_scores(review)["compound"]
        if score >= 0.05:
            sentiments.append("positive")
        elif score <= -0.05:
            sentiments.append("negative")
        else:
            sentiments.append("neutral")
    return sentiments


def summarize_reviews(reviews):
    summarized_reviews = []
    month_names = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december', 'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    rating_words = ['rating', 'rated', 'rate']

    for review in reviews:
    
        clean_review = re.sub(r'\b\d+\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{1,2}-\d{1,2}-\d{2,4}\b|\b(?:' + '|'.join(month_names) + r')\b|\b(?:' + '|'.join(rating_words) + r')\b|[./,\"\'\';:()*,%]|days\s+ago', '', review, flags=re.IGNORECASE)
        
        clean_review = re.sub(r'@\w+\b', '', clean_review)
        
        clean_review = re.sub(r'#\w+', '', clean_review)
        
        clean_review = re.sub(r'\b\d\.\d\b', '', clean_review)
    
        clean_review = re.sub(r'by\s+\w+', '', clean_review, flags=re.IGNORECASE)
        
        clean_review = re.sub(r'[$]', '', clean_review)

        try:
            if detect(clean_review) != 'en':
                clean_review = ''
        except LangDetectException as e:
            print("Language detection error:", e)
            clean_review = ''
        clean_review = re.sub(r'\b\d+\b', '', clean_review)
        clean_review = clean_review.strip()

        if not clean_review.isdigit() and not clean_review.isnumeric():
            summarized_reviews.append(clean_review)

    return summarized_reviews


def generate_word_cloud(reviews, movie_title):
    text = ' '.join(reviews)
    wordcloud = WordCloud(width=800, height=400, background_color='white').generate(text)
    
    movie_folder = os.path.join(RESULTS_DIR, movie_title)
    if not os.path.exists(movie_folder):
        os.makedirs(movie_folder)
    
    wordcloud_filename = f"{movie_title}_wordcloud.png"
    wordcloud_path = os.path.join(movie_folder, wordcloud_filename)
    wordcloud.to_file(wordcloud_path)

    static_wordcloud_path = os.path.join("static", wordcloud_filename)
    wordcloud.to_file(static_wordcloud_path)

    with open(os.path.join(movie_folder, "summarized_reviews.txt"), "w", encoding="utf-8") as file:
        for review in reviews:
            file.write(review + "\n")

    return wordcloud_filename

class MovieSearchForm(FlaskForm):
    movie_title = StringField('Movie Title', validators=[DataRequired()])

@app.route('/', methods=['GET', 'POST'])
def index():
    form = MovieSearchForm()
    movies = [movie_folder for movie_folder in os.listdir(RESULTS_DIR) if os.path.isdir(os.path.join(RESULTS_DIR, movie_folder))]
    matched_movies = []

    if form.validate_on_submit():
        movie_title = form.movie_title.data
        if movie_title:
            for movie in movies:
                if movie_title.lower() in movie.lower():
                    matched_movies.append(movie)
            if not matched_movies:
                reviews = scrape_reviews(movie_title)
                if reviews:
                    sentiments, plot_path = analyze_and_save_sentiments(reviews, movie_title)
                    summarized_reviews = summarize_reviews(reviews)
                    wordcloud_filename = generate_word_cloud(reviews, movie_title)
                    precision, recall, f_score = calculate_metrics(sentiments)
                    movies.append(movie_title)
                    return render_template('movie.html', movie_title=movie_title, sentiments=sentiments,
                                           summarized_reviews=summarized_reviews,
                                           wordcloud_filename=wordcloud_filename, precision=precision,
                                           recall=recall, f_score=f_score, sentiment_plot_path=plot_path)
                else:
                    return render_template('error.html', message="No reviews found for the movie.")
    
    return render_template('index.html', form=form, movies=movies, matched_movies=matched_movies)

def analyze_and_save_sentiments(reviews, movie_title):
    sentiments = analyze_sentiment(reviews)
    movie_folder = os.path.join("results", movie_title)
    os.makedirs(movie_folder, exist_ok=True)

    sentiment_counts = Counter(sentiments)
    plt.bar(sentiment_counts.keys(), sentiment_counts.values())
    plt.xlabel('Sentiment')
    plt.ylabel('Count')
    plt.title('Sentiment Analysis')
    plt.xticks(rotation=45)
    plot_filename = f"{movie_title}_sentiment_analysis_plot.png"
    plot_path_movie_folder = os.path.join(movie_folder, plot_filename)
    plot_path_static = os.path.join("static", plot_filename)
    plt.savefig(plot_path_movie_folder)
    plt.savefig(plot_path_static)
    plt.close()

    with open(os.path.join(movie_folder, "sentiments.txt"), "w") as file:
        for sentiment in sentiments:
            file.write(sentiment + "\n")
    return sentiments, plot_filename

@app.route('/existing_movie/<movie_title>')
def existing_movie(movie_title):
    movie_folder = os.path.join(RESULTS_DIR, movie_title)
    if not os.path.exists(movie_folder):
        return render_template('error.html', message="Results not found for the movie.")

    with open(os.path.join(movie_folder, "sentiments.txt"), "r", encoding="utf-8") as file:
        sentiments = file.read().splitlines()
    
    sentiment_counts = Counter(sentiments)
    sentiment_counts_dict = dict(sentiment_counts) 
    
    with open(os.path.join(movie_folder, "summarized_reviews.txt"), "r", encoding="utf-8") as file:
        summarized_reviews = file.read().splitlines()
    
    wordcloud_filename = f"{movie_title}_wordcloud.png"
    sentiment_plot_filename = f"{movie_title}_sentiment_analysis_plot.png"

    precision, recall, f_score = calculate_metrics(sentiments)
    return render_template('existing_movie.html', movie_title=movie_title, sentiments=sentiments,
                            summarized_reviews=summarized_reviews, wordcloud_filename=wordcloud_filename,
                            precision=precision, recall=recall, f_score=f_score, sentiment_plot_path=sentiment_plot_filename,
                            sentiment_counts=sentiment_counts_dict)

def calculate_metrics(sentiments):
    ground_truth_sentiments = ["positive"] * len(sentiments)

    precision = precision_score(ground_truth_sentiments, sentiments, average="macro", zero_division=0)
    recall = recall_score(ground_truth_sentiments, sentiments, average="macro", zero_division=0)
    f_score = f1_score(ground_truth_sentiments, sentiments, average="macro", zero_division=0)

    return precision, recall, f_score

@app.route('/movie_static/<movie_title>/<path:filename>')
def movie_static(movie_title, filename):
    return send_from_directory(os.path.join(RESULTS_DIR, movie_title), filename)

@app.route('/search_keyword', methods=['POST'])
def search_keyword():
    keyword = request.form.get('keyword')
    movie_title = request.form.get('movie_title')
    if keyword and movie_title:
        movie_folder = os.path.join(RESULTS_DIR, movie_title)
        if not os.path.exists(movie_folder):
            return render_template('error.html', message="Results not found for the movie.")
        
        with open(os.path.join(movie_folder, "summarized_reviews.txt"), "r", encoding="utf-8") as file:
            reviews = file.read().splitlines()
        
        sentiments, plot_path = analyze_and_save_sentiments(reviews, movie_title)
        summarized_reviews = summarize_reviews(reviews) 
        wordcloud_filename = generate_word_cloud(reviews, movie_title)
        precision, recall, f_score = calculate_metrics(sentiments)
        
        keyword_count = sum(1 for review in summarized_reviews if keyword.lower() in review.lower())

   
        exact_matches = [review for review in summarized_reviews if keyword.lower() == review.lower()]
        variations_matches = [review for review in summarized_reviews if keyword.lower() in review.lower() and keyword.lower() != review.lower()]
        phrase_matches = [review for review in summarized_reviews if keyword.lower() in review.lower() and keyword.lower() == review.lower()]
        all_matches = exact_matches + variations_matches + phrase_matches

       
        return render_template('movie.html', movie_title=movie_title, sentiments=sentiments,
                               summarized_reviews=summarized_reviews, wordcloud_filename=wordcloud_filename,
                               precision=precision, recall=recall, f_score=f_score, sentiment_plot_path=plot_path,
                               keyword=keyword, keyword_count=keyword_count,
                               exact_matches=exact_matches, variations_matches=variations_matches,
                               phrase_matches=phrase_matches, all_matches=all_matches)
    else:
        return render_template('error.html', message="Invalid request.")





if __name__ == '__main__':
    app.run(debug=True)
