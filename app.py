from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)
DATABASE = "database.db"


def get_db_connection():
    """
    Create a database connection.
    row_factory lets us access columns by name (expense["amount"]).
    """
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create expenses table if it does not exist yet."""
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            note TEXT,
            expense_date TEXT NOT NULL,
            transaction_type TEXT NOT NULL DEFAULT 'chi',
            payment_method TEXT NOT NULL DEFAULT 'tien_mat'
        )
        """
    )

    # Simple migration for old databases that do not have transaction_type yet.
    columns = conn.execute("PRAGMA table_info(expenses)").fetchall()
    column_names = [column["name"] for column in columns]
    if "transaction_type" not in column_names:
        conn.execute(
            "ALTER TABLE expenses ADD COLUMN transaction_type TEXT NOT NULL DEFAULT 'chi'"
        )
    if "payment_method" not in column_names:
        conn.execute(
            "ALTER TABLE expenses ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'tien_mat'"
        )

    conn.commit()
    conn.close()


@app.route("/")
def index():
    """
    Main page:
    - optional date filtering
    - list expenses
    - show total spending for filtered data
    """
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")

    conn = get_db_connection()
    query = "SELECT * FROM expenses"
    params = []

    if start_date and end_date:
        query += " WHERE expense_date BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    elif start_date:
        query += " WHERE expense_date >= ?"
        params.append(start_date)
    elif end_date:
        query += " WHERE expense_date <= ?"
        params.append(end_date)

    query += " ORDER BY expense_date DESC, id DESC"
    expenses = conn.execute(query, params).fetchall()

    # Current balances (all transactions, not limited by date filter).
    balances_row = conn.execute(
        """
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN payment_method = 'tien_mat' AND transaction_type = 'thu' THEN amount
                    WHEN payment_method = 'tien_mat' AND transaction_type = 'chi' THEN -amount
                    ELSE 0
                END
            ), 0) AS cash_balance,
            COALESCE(SUM(
                CASE
                    WHEN payment_method = 'ngan_hang' AND transaction_type = 'thu' THEN amount
                    WHEN payment_method = 'ngan_hang' AND transaction_type = 'chi' THEN -amount
                    ELSE 0
                END
            ), 0) AS bank_balance
        FROM expenses
        """
    ).fetchone()

    cash_balance = balances_row["cash_balance"]
    bank_balance = balances_row["bank_balance"]

    total_income = sum(
        expense["amount"] for expense in expenses if expense["transaction_type"] == "thu"
    )
    total_expense = sum(
        expense["amount"] for expense in expenses if expense["transaction_type"] == "chi"
    )
    total = total_income - total_expense

    # Weekly and monthly summaries for a quick statistics overview.
    week_total_row = conn.execute(
        """
        SELECT COALESCE(
            SUM(CASE
                WHEN transaction_type = 'thu' THEN amount
                ELSE -amount
            END), 0
        ) AS total
        FROM expenses
        WHERE strftime('%Y-W%W', expense_date) = strftime('%Y-W%W', 'now', 'localtime')
        """
    ).fetchone()
    month_total_row = conn.execute(
        """
        SELECT COALESCE(
            SUM(CASE
                WHEN transaction_type = 'thu' THEN amount
                ELSE -amount
            END), 0
        ) AS total
        FROM expenses
        WHERE substr(expense_date, 1, 7) = strftime('%Y-%m', 'now', 'localtime')
        """
    ).fetchone()

    week_total = week_total_row["total"]
    month_total = month_total_row["total"]

    # Running balances after each transaction (based on full history).
    history_rows = conn.execute(
        """
        SELECT id, amount, transaction_type, payment_method
        FROM expenses
        ORDER BY expense_date ASC, id ASC
        """
    ).fetchall()

    running_cash = 0.0
    running_bank = 0.0
    balance_after_by_id = {}

    for row in history_rows:
        signed_amount = row["amount"] if row["transaction_type"] == "thu" else -row["amount"]
        if row["payment_method"] == "tien_mat":
            running_cash += signed_amount
        else:
            running_bank += signed_amount

        balance_after_by_id[row["id"]] = {
            "cash_after": running_cash,
            "bank_after": running_bank,
            "total_after": running_cash + running_bank,
        }

    # Convert rows to dict so we can attach display-only values.
    expenses_with_balance = []
    for expense in expenses:
        expense_dict = dict(expense)
        balance_after = balance_after_by_id.get(expense["id"], {})
        expense_dict["cash_after"] = balance_after.get("cash_after", 0.0)
        expense_dict["bank_after"] = balance_after.get("bank_after", 0.0)
        expense_dict["total_after"] = balance_after.get("total_after", 0.0)
        expenses_with_balance.append(expense_dict)

    conn.close()

    return render_template(
        "index.html",
        expenses=expenses_with_balance,
        total=total,
        total_income=total_income,
        total_expense=total_expense,
        cash_balance=cash_balance,
        bank_balance=bank_balance,
        week_total=week_total,
        month_total=month_total,
        start_date=start_date,
        end_date=end_date,
    )


@app.route("/add", methods=["POST"])
def add_expense():
    """Add a new expense from form data."""
    amount = request.form.get("amount")
    category = request.form.get("category")
    note = request.form.get("note", "")
    expense_date = request.form.get("expense_date")
    transaction_type = request.form.get("transaction_type", "chi")
    payment_method = request.form.get("payment_method", "tien_mat")

    # Basic validation so the app stays beginner-friendly but safe.
    try:
        amount = float(amount)
        datetime.strptime(expense_date, "%Y-%m-%d")
        if transaction_type not in {"thu", "chi"}:
            return redirect(url_for("index"))
        if payment_method not in {"tien_mat", "ngan_hang"}:
            return redirect(url_for("index"))
    except (ValueError, TypeError):
        return redirect(url_for("index"))

    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO expenses (amount, category, note, expense_date, transaction_type, payment_method)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (amount, category, note, expense_date, transaction_type, payment_method),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/delete/<int:expense_id>", methods=["POST"])
def delete_expense(expense_id):
    """Delete an expense by its ID."""
    conn = get_db_connection()
    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
def edit_expense(expense_id):
    """
    GET  -> show edit form with existing expense values
    POST -> update expense and return to home page
    """
    conn = get_db_connection()
    expense = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()

    if not expense:
        conn.close()
        return redirect(url_for("index"))

    if request.method == "POST":
        amount = request.form.get("amount")
        category = request.form.get("category")
        note = request.form.get("note", "")
        expense_date = request.form.get("expense_date")
        transaction_type = request.form.get("transaction_type", "chi")
        payment_method = request.form.get("payment_method", "tien_mat")

        try:
            amount = float(amount)
            datetime.strptime(expense_date, "%Y-%m-%d")
            if transaction_type not in {"thu", "chi"}:
                conn.close()
                return redirect(url_for("edit_expense", expense_id=expense_id))
            if payment_method not in {"tien_mat", "ngan_hang"}:
                conn.close()
                return redirect(url_for("edit_expense", expense_id=expense_id))
        except (ValueError, TypeError):
            conn.close()
            return redirect(url_for("edit_expense", expense_id=expense_id))

        conn.execute(
            """
            UPDATE expenses
            SET amount = ?, category = ?, note = ?, expense_date = ?, transaction_type = ?, payment_method = ?
            WHERE id = ?
            """,
            (amount, category, note, expense_date, transaction_type, payment_method, expense_id),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    conn.close()
    return render_template("edit.html", expense=expense)


@app.route("/stats/monthly")
def monthly_stats():
    """
    Return monthly totals as JSON for Chart.js.
    Example output:
    [{ "month": "2026-04", "total": 150.5 }, ...]
    """
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT
            substr(expense_date, 1, 7) AS month,
            SUM(CASE WHEN transaction_type = 'thu' THEN amount ELSE -amount END) AS total
        FROM expenses
        GROUP BY month
        ORDER BY month ASC
        """
    ).fetchall()
    conn.close()

    data = [{"month": row["month"], "total": row["total"]} for row in rows]
    return jsonify(data)


@app.route("/stats/weekly")
def weekly_stats():
    """
    Return weekly totals as JSON for Chart.js.
    Example output:
    [{ "week": "2026-W14", "total": 120.0 }, ...]
    """
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT
            strftime('%Y-W%W', expense_date) AS week,
            SUM(CASE WHEN transaction_type = 'thu' THEN amount ELSE -amount END) AS total
        FROM expenses
        GROUP BY week
        ORDER BY week ASC
        """
    ).fetchall()
    conn.close()

    data = [{"week": row["week"], "total": row["total"]} for row in rows]
    return jsonify(data)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
