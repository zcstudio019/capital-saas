def calculate_loan_cost(loan_amount: float, annual_rate: float, months: int,
                        repayment_method: str = "interest_first") -> dict:
    principal = max(float(loan_amount), 0)
    months = max(int(months), 1)
    monthly_rate = max(float(annual_rate), 0) / 100 / 12
    schedule, total_interest = [], 0.0
    balance = principal
    if repayment_method == "equal_installment":
        payment = principal / months if monthly_rate == 0 else principal * monthly_rate * (1 + monthly_rate) ** months / ((1 + monthly_rate) ** months - 1)
        for period in range(1, months + 1):
            interest = balance * monthly_rate; paid_principal = payment - interest; balance = max(0, balance - paid_principal)
            total_interest += interest; schedule.append({"month": period, "principal": round(paid_principal, 2), "interest": round(interest, 2), "payment": round(payment, 2), "balance": round(balance, 2)})
    elif repayment_method == "equal_principal":
        paid_principal = principal / months
        for period in range(1, months + 1):
            interest = balance * monthly_rate; payment = paid_principal + interest; balance = max(0, balance - paid_principal)
            total_interest += interest; schedule.append({"month": period, "principal": round(paid_principal, 2), "interest": round(interest, 2), "payment": round(payment, 2), "balance": round(balance, 2)})
    elif repayment_method == "lump_sum":
        total_interest = principal * monthly_rate * months
        for period in range(1, months + 1):
            payment = principal + total_interest if period == months else 0
            schedule.append({"month": period, "principal": principal if period == months else 0,
                             "interest": total_interest if period == months else 0, "payment": payment,
                             "balance": principal if period < months else 0})
    else:
        interest = principal * monthly_rate; total_interest = interest * months
        for period in range(1, months + 1):
            payment = interest + (principal if period == months else 0)
            schedule.append({"month": period, "principal": principal if period == months else 0,
                             "interest": round(interest, 2), "payment": round(payment, 2),
                             "balance": principal if period < months else 0})
    max_payment = max((row["payment"] for row in schedule), default=0)
    pressure = "high" if max_payment > principal * 0.3 else "medium" if max_payment > principal * 0.1 else "low"
    return {"monthly_payment": round(sum(row["payment"] for row in schedule) / months, 2),
            "total_interest": round(total_interest, 2), "total_repayment": round(principal + total_interest, 2),
            "cashflow_pressure_level": pressure, "repayment_schedule": schedule}
