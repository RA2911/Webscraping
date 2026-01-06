from flask import Flask, request, render_template
from scraper import scrape_clean_text

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def home():
    text = None
    if request.method == "POST":
        url = request.form.get("url")
        if url:
            try:
                text = scrape_clean_text(url)
            except Exception as e:
                text = f"Error: {e}"
    return render_template("index.html", text=text)

if __name__ == "__main__":
    app.run(debug=True)
