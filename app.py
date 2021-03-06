import os
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():

    entries = db.execute("SELECT * FROM bought WHERE user_id=?", session["user_id"])
    users = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
    return render_template("index.html", entries=entries, users=users)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("choose a valid stock name")
        stock = lookup(request.form.get("symbol").upper())
        
        if stock is None:
            return apology("invalid stock name", 400)
        if not (request.form.get("shares")).isdigit():
            return apology("invalid shares", 400)
        shares = int(request.form.get("shares"))
        rows = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
        cash = rows[0]["cash"]
        total = stock["price"] * shares
        newCash = cash - total
        if newCash < 0:
            return apology("you do not have enough money to purchase this")
        
        # if symbol is not in the database, then we create a new row in table, otherwise we just add on to previous bought shares
        prevStocks = db.execute("SELECT symbol FROM bought WHERE user_id=?", session["user_id"])
        list_of_bool = [True for elem in prevStocks if stock["symbol"] in elem.values()]
        if not prevStocks or not any(list_of_bool):
            db.execute("INSERT INTO bought (symbol, shares, price, total, name, user_id) VALUES(?,?,?,?,?,?)", 
                       stock["symbol"], shares, stock["price"], total, stock["name"], session["user_id"])

        else:
            prevValues = db.execute("SELECT shares, price, total FROM bought WHERE user_id=? AND symbol=?", 
                                    session["user_id"], stock["symbol"])
            db.execute("UPDATE bought SET shares=?, total=? WHERE user_id=? AND symbol=?", shares + 
                       prevValues[0]["shares"], total + prevValues[0]["total"], session["user_id"], stock["symbol"])

        db.execute("INSERT INTO history (shares, symbol, price, users_id) VALUES(?,?,?,?)", 
                   shares, stock["symbol"], stock["price"], session["user_id"])
        db.execute("UPDATE users SET cash=:newCash WHERE id=:id", newCash=newCash, id=session["user_id"])
        flash("Bought!")
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")  # Get is there by default
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("SELECT time, shares, symbol, price FROM history WHERE users_id=?", session["user_id"])
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if request.form.get("n_p") or request.form.get("old_name"):
            if not request.form.get("n_p") or not request.form.get("old_name"):
                return apology("Fill out required fields", 400)
            old_password = db.execute("SELECT hash FROM users WHERE username=?", request.form.get("old_name"))
            if check_password_hash(old_password[0]["hash"], request.form.get("n_p")):
                return apology("This is your already existing password", 400)
            
            db.execute("UPDATE users SET hash=?", generate_password_hash(
                request.form.get("n_p"), method='pbkdf2:sha256', salt_length=8))
            flash("Password Changed!")
            return redirect("/")
        
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username=?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        message = lookup(request.form.get("symbol"))
        if not message:
            return apology("invalid symbol")
            
        return render_template("quoted.html", quote=message)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    session.clear()

    if request.method == "POST":

        if not request.form.get("username"):
            return apology("must provide username", 400)

        elif not request.form.get("password"):
            return apology("must provide password", 400)

        elif request.form.get("confirmation") != request.form.get("password"):
            return apology("invalid confirmation password", 400)

        rows = db.execute("SELECT * FROM users WHERE username=?", request.form.get("username"))
        if len(rows) != 0:
            return apology("invalid username", 400)
        
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", request.form.get("username"),
                   generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=8))

        rows1 = db.execute("SELECT * FROM users WHERE username=?", request.form.get("username"))
        if not check_password_hash(rows1[0]["hash"], request.form.get("password")):
            return apology("invalid password", 400)

        session["user_id"] = rows1[0]["id"]
        flash("Registered!")
        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    old = db.execute("SELECT * FROM bought WHERE user_id=?", session["user_id"])

    if request.method == "POST":
        if not request.form.get("shares"):
            return apology("get valid num of shares")
        if not request.form.get("symbol"):
            return apology("choose stock name which you want to sell")
        # subtract s amount of shares and then calculate the new total, and cash. If more shares are sold then are availiable return apology
        subtract_shares = int(request.form.get("shares"))
        old_stock = db.execute("SELECT * FROM bought WHERE user_id=? AND symbol=?", session["user_id"], request.form.get("symbol"))

        if subtract_shares > old_stock[0]["shares"]:
            return apology("trying to sell too many shares", 400)

        stock = lookup(request.form.get("symbol").upper())
        total = (old_stock[0]["shares"] - subtract_shares) * stock["price"]

        difference = old_stock[0]["total"] - total
        newCash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
        db.execute("UPDATE bought SET shares=?, total=? WHERE user_id=? AND symbol=?", 
                   old_stock[0]["shares"] - subtract_shares, total, session["user_id"], old_stock[0]["symbol"])
        db.execute("INSERT INTO history (shares, symbol, price, users_id) VALUES(?,?,?,?)", 
                   0-subtract_shares, stock["symbol"], stock["price"], session["user_id"])
        db.execute("UPDATE users SET cash=? WHERE id=?", newCash[0]["cash"] + difference, session["user_id"])
        flash("Sold!")
        return redirect("/")

    else:
        return render_template("sell.html", stocks=old)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
