"""ADIB Egypt's own QA scoresheet and call categories, from "ADIB_Call_Center_ScoreSheet & Calls Categories.xlsx".
Names are kept exactly as ADIB wrote them (they match their call-activity tree).

QA score for ADIB = 100 minus the points of every mistake found in the call (each mistake counted once per call),
never below 0. A call with an End User, Business Critical or Compliance Critical mistake is also flagged."""

SOURCE = "ADIB scoresheet 2026-11"

# severity: (label, points off per mistake, critical)
SEVERITY = {"compliance": ("Compliance Critical", 25, True), "business": ("Business Critical", 20, True),
            "end_user": ("End User", 15, True), "non_critical": ("Non Critical", 5, False)}

# category groups (the prefixes in ADIB's list)
GROUPS = {"Account": "Accounts", "Sukuk": "Sukuk", "Auto": "Auto finance", "LME": "LME", "CBC": "CBC (credit cards)",
          "D.C": "Debit cards", "IB": "Internet banking", "E-Wallet": "E-Wallet", "Instapay": "InstaPay", "Other": "Other"}

# (code, name exactly as in the sheet, group)
CATEGORIES = [
    ('account_balance', 'Account-Balance', 'Account'),
    ('account_sms', 'Account-SMS', 'Account'),
    ('account_linked_with_card', 'Account-Linked With Card', 'Account'),
    ('account_update', 'Account- Update', 'Account'),
    ('account_profit_inquiry', 'Account-Profit Inquiry', 'Account'),
    ('account_hold_inquiry', 'Account- Hold Inquiry', 'Account'),
    ('account_status_inquiry', 'Account-Status Inquiry', 'Account'),
    ('account_iban_and_swift_code', 'Account- IBAN and Swift Code', 'Account'),
    ('account_transfer_inquiry', 'Account-Transfer Inquiry', 'Account'),
    ('account_trx_inquiry', 'Account-TRX Inquiry', 'Account'),
    ('account_fees_inquiry', 'Account-Fees Inquiry', 'Account'),
    ('account_chq_inquiry', 'Account -Chq - Inquiry', 'Account'),
    ('account_wasel_sales', 'Account-Wasel sales', 'Account'),
    ('account_complaint', 'Account- complaint', 'Account'),
    ('account_follow_up_on_request', 'Account-Follow up on Request', 'Account'),
    ('account_follow_up_on_complaint', 'Account-Follow up on complaint', 'Account'),
    ('sukuk_sales', 'Sukuk-Sales', 'Sukuk'),
    ('sukuk_redemption', 'Sukuk-Redemption', 'Sukuk'),
    ('auto_general_info', 'Auto - General Info', 'Auto'),
    ('auto_file', 'Auto - File', 'Auto'),
    ('auto_verification', 'Auto - Verification', 'Auto'),
    ('auto_partial_damage_letter_total_loss', 'Auto - Partial damage Letter -Total Loss', 'Auto'),
    ('auto_retention_requset_early_sattalment', 'Auto - Retention Requset "early Sattalment', 'Auto'),
    ('auto_balance_installment', 'Auto - Balance Installment', 'Auto'),
    ('auto_renwal_letter', 'Auto - Renwal Letter', 'Auto'),
    ('auto_release_letter', 'Auto - Release Letter', 'Auto'),
    ('auto_clearance_letter', 'Auto -Clearance Letter', 'Auto'),
    ('auto_certificat_of_libilte', 'Auto -Certificat Of Libilte', 'Auto'),
    ('auto_follow_up_on_request', 'Auto-Follow up on Request', 'Auto'),
    ('auto_follow_up_on_complaint', 'Auto-Follow up on complaint', 'Auto'),
    ('auto_complaint', 'Auto Complaint', 'Auto'),
    ('auto_new_sales', 'Auto-New Sales', 'Auto'),
    ('auto_used_sales', 'Auto-Used Sales', 'Auto'),
    ('lme_amount_booking', 'LME- Amount Booking', 'LME'),
    ('lme_balance_installment_inquiry', 'LME - Balance Installment Inquiry', 'LME'),
    ('lme_installment_inquiry', 'LME - Installment Inquiry', 'LME'),
    ('lme_retention_requset', 'LME- Retention Requset', 'LME'),
    ('lme_balance_installment', 'LME - Balance Installment', 'LME'),
    ('lme_verification', 'LME- Verification', 'LME'),
    ('lme_follow_up_on_request', 'LME-Follow up on Request', 'LME'),
    ('lme_complaint', 'LME-complaint', 'LME'),
    ('lme_follow_up_on_complaint', 'LME-Follow up on complaint', 'LME'),
    ('lme_clearance_letter', 'LME -Clearance Letter', 'LME'),
    ('lme_certificat_of_libilte', 'LME -Certificat Of Libilte', 'LME'),
    ('lme_file', 'LME-File', 'LME'),
    ('lme_sales', 'LME -Sales', 'LME'),
    ('cbc_sales', 'CBC- Sales', 'CBC'),
    ('cbc_inquiry_on_balance', 'CBC -Inquiry on Balance', 'CBC'),
    ('cbc_buy_out', 'CBC-Buy out', 'CBC'),
    ('cbc_fees_inquiry', 'CBC -Fees Inquiry', 'CBC'),
    ('cbc_activation', 'CBC - Activation', 'CBC'),
    ('cbc_replacement_activation', 'CBC- Replacement Activation', 'CBC'),
    ('cbc_wrof', 'CBC - WROF', 'CBC'),
    ('cbc_issue', 'CBC- Issue', 'CBC'),
    ('cbc_supplementary', 'CBC -Supplementary', 'CBC'),
    ('cbc_statement_e_statement', 'CBC-Statement -E-statement', 'CBC'),
    ('cbc_clearance_letter', 'CBC - Clearance Letter', 'CBC'),
    ('cbc_certificate_of_liabilities_letter', 'CBC - Certificate of liabilities Letter', 'CBC'),
    ('cbc_retention_requset', 'CBC - Retention Requset', 'CBC'),
    ('cbc_activation_renewal', 'CBC - Activation Renewal', 'CBC'),
    ('cbc_complaints', 'CBC - Complaints', 'CBC'),
    ('cbc_blocked_and_replacement_requset', 'CBC - Blocked and Replacement Requset', 'CBC'),
    ('cbc_balance_retention_requsat', 'CBC - Balance & Retention Requsat', 'CBC'),
    ('cbc_pin_code_error', 'CBC - Pin Code Error', 'CBC'),
    ('cbc_balance_activation_renewal', 'CBC - Balance &Activation Renewal', 'CBC'),
    ('cbc_delivery_request', 'CBC -Delivery Request', 'CBC'),
    ('cbc_delivery_status', 'CBC -Delivery Status', 'CBC'),
    ('cbc_renewal_status', 'CBC - Renewal status', 'CBC'),
    ('cbc_follow_up_on_request', 'CBC-Follow up on Request', 'CBC'),
    ('cbc_follow_up_on_complaint', 'CBC-Follow up on complaint', 'CBC'),
    ('cbc_pin_code_delivery', 'CBC - Pin Code Delivery', 'CBC'),
    ('cbc_trx', 'CBC-TRX', 'CBC'),
    ('cbc_payment', 'CBC-Payment', 'CBC'),
    ('cbc_3d_secured', 'CBC-3d secured', 'CBC'),
    ('cbc_epp', 'CBC-EPP', 'CBC'),
    ('cbc_travel_documents', 'CBC-Travel Documents', 'CBC'),
    ('cbc_open_international_limit', 'CBC-Open international limit', 'CBC'),
    ('cbc_status', 'CBC-Status', 'CBC'),
    ('cbc_feedback', 'CBC-Feedback', 'CBC'),
    ('cbc_changing_mobile_number', 'CBC-Changing mobile number', 'CBC'),
    ('cbc_rerun', 'CBC-Rerun', 'CBC'),
    ('cbc_direct_debit', 'CBC-Direct Debit', 'CBC'),
    ('cbc_add_e_mail', 'CBC-Add E-Mail', 'CBC'),
    ('cbc_insurance', 'CBC-Insurance', 'CBC'),
    ('cbc_closure', 'CBC-Closure', 'CBC'),
    ('d_c_activation', 'D.C - Activation', 'D.C'),
    ('d_c_renewal_activation', 'D.C -Renewal Activation', 'D.C'),
    ('d_c_status', 'D.C -Status', 'D.C'),
    ('d_c_transaction_inquiry', 'D.C transaction Inquiry', 'D.C'),
    ('d_c_acc_linkage', 'D.C - ACC Linkage', 'D.C'),
    ('d_c_issue', 'D.C - Issue', 'D.C'),
    ('d_c_replacement_activation', 'D.C-Replacement Activation', 'D.C'),
    ('d_c_otac', 'D.C- OTAC', 'D.C'),
    ('d_c_reset_pin', 'D.C- Reset Pin', 'D.C'),
    ('d_c_supplementary_activation', 'D.C- Supplementary Activation', 'D.C'),
    ('d_c_closed_and_replacement', 'D.C- Closed and Replacement', 'D.C'),
    ('dc_complaint', 'DC-Complaint', 'D.C'),
    ('complaint_followup', 'Complaint Followup', 'Other'),
    ('d_c_delivery_inquiry', 'D.C- Delivery Inquiry', 'D.C'),
    ('d_c_replacement_inquiry', 'D.C- Replacement Inquiry', 'D.C'),
    ('d_c_delivery_requst', 'D.C- Delivery Requst', 'D.C'),
    ('d_c_error', 'D.C- Error', 'D.C'),
    ('d_c_atm_dep_request', 'D.C-ATM DEP Request', 'D.C'),
    ('d_c_atm_withdrawal_sr', 'D.C-ATM Withdrawal SR', 'D.C'),
    ('d_c_follow_up_on_request', 'D.C-Follow up on Request', 'D.C'),
    ('d_c_follow_up_on_complaint', 'D.C-Follow up on complaint', 'D.C'),
    ('d_c_feedback', 'D.C-Feedback', 'D.C'),
    ('ib_activation', 'IB- Activation', 'IB'),
    ('ib_reset_pin_code', 'IB - Reset Pin Code', 'IB'),
    ('ib_transfer', 'IB - Transfer', 'IB'),
    ('ib_error_request', 'IB - Error Request', 'IB'),
    ('ib_new_complaint', 'IB- New Complaint', 'IB'),
    ('ib_token_activation', 'IB-Token Activation', 'IB'),
    ('ib_new_request', 'IB- New Request', 'IB'),
    ('ib_follow_up_on_request', 'IB-Follow up on Request', 'IB'),
    ('ib_follow_up_on_complaint', 'IB-Follow up on complaint', 'IB'),
    ('e_wallet_activation', 'E-Wallet - Activation', 'E-Wallet'),
    ('e_wallet_reset_pass', 'E-Wallet - Reset pass', 'E-Wallet'),
    ('e_wallet_trx_issue', 'E-Wallet -TRX Issue', 'E-Wallet'),
    ('e_wallet_blocking', 'E-Wallet - Blocking', 'E-Wallet'),
    ('instapay_registering', 'Instapay-Registering', 'Instapay'),
    ('instapay_trx', 'Instapay-TRX', 'Instapay'),
    ('instapay_complaint', 'Instapay-Complaint', 'Instapay'),
    ('instapay_issue', 'Instapay-Issue', 'Instapay'),
    ('instapay_good_faith', 'Instapay-Good faith', 'Instapay'),
    ('confirmation_call', 'Confirmation call', 'Other'),
    ('currency_withdrawal', 'Currency-Withdrawal', 'Other'),
    ('atm_service', 'ATM-Service', 'Other'),
    ('branches_working_hours', 'Branches - Working hours', 'Other'),
    ('branches_address', 'Branches - Address', 'Other'),
]

# (code, mistake exactly as in the sheet, severity)
ERRORS = [
    ('delay_in_updating_the_customer', 'Delay in updating the customer', 'end_user'),
    ('interrupting_the_customer', 'Interrupting the customer', 'end_user'),
    ('sharp_aggressive_voice_tone', 'Sharp/aggressive voice tone', 'end_user'),
    ('rude_behavior_blaming_provoking_customer', 'Rude behavior/Blaming & Provoking customer', 'end_user'),
    ('showing_carelessness_to_cancelation_requests', 'Showing carelessness to cancelation requests', 'end_user'),
    ('didnt_confirm_customers_solution_accurately', "Didn't confirm customer's solution/accurately", 'end_user'),
    ('no_trouble_shooting_wrong_steps', 'No trouble shooting/Wrong steps', 'end_user'),
    ('didnt_follow_search_process_ec', "Didn't Follow Search process (EC)", 'end_user'),
    ('didnt_check_system_history', "Didn't check system history", 'end_user'),
    ('didnt_follow_up_when_required', 'Didn’t follow up when required', 'end_user'),
    ('fcr', 'FCR', 'end_user'),
    ('unnecessary_hold_unnecessary_dead_air', 'Unnecessary Hold / Unnecessary Dead Air', 'end_user'),
    ('didnt_offer_ivr', "Didn't offer IVR", 'end_user'),
    ('delay_follow_up', 'Delay follow up', 'end_user'),
    ('didnt_log_or_update_complaint_request', "Didn't log or Update Complaint/ Request", 'end_user'),
    ('missing_wrong_complaint_or_request_assign_or_description', 'Missing/Wrong complaint or request assign or description / Enter wrong data', 'end_user'),
    ('wrong_incomplete_e_mail', 'Wrong/incomplete E-mail', 'end_user'),
    ('didnt_describe_or_handle_information_service_levels_fee', "Didn't describe or handle information/ service levels / fees / Promotion / offers using K-base", 'end_user'),
    ('disconnected_the_call', 'Disconnected the call', 'end_user'),
    ('no_transfer_wrong_transfer', 'No transfer/wrong transfer', 'end_user'),
    ('didnt_wait_for_proper_time_before_ending_call_didnt_ha', "Didn't wait for proper time before ending call/Didn't hangup after 30s of closing", 'end_user'),
    ('didnt_ask_about_required_data', "Didn't Ask about required data", 'business'),
    ('didnt_log_call_activity_wrong_call_activity_tree_type_m', "Didn't log call activity/Wrong call activity tree/type , missing or wrong", 'business'),
    ('late_incomplete_verification', 'Late / incomplete verification', 'compliance'),
    ('didnt_welcome_the_customer', "Didn't Welcome the customer", 'non_critical'),
    ('no_need_over_verification', 'No need / Over verification', 'non_critical'),
    ('dead_air', 'Dead Air', 'non_critical'),
    ('ineffective_questions_info', 'Ineffective questions/Info', 'non_critical'),
    ('didnt_collect_the_data_in_smart_way', 'Didn’t Collect the Data in Smart way', 'non_critical'),
    ('unable_to_explain', 'Unable to explain', 'non_critical'),
    ('didnt_reflect_with_the_customer', "Didn't reflect with the customer", 'non_critical'),
    ('not_empathic', 'Not Empathic', 'non_critical'),
    ('didnt_apologize_to_customer', 'Didn’t apologize to customer', 'non_critical'),
    ('assumption', 'Assumption', 'non_critical'),
    ('not_focused_let_customer_repeat_the_information', 'Not focused/Let customer repeat the information', 'non_critical'),
    ('scripted_monotony_sleepy_bored_cold_unwelcome_unfriendly', 'Scripted/Monotony/sleepy/bored/cold/unwelcome/unfriendly tone', 'non_critical'),
    ('very_fast_unclear', 'Very fast/unclear', 'non_critical'),
    ('not_confident_hesitant', 'Not confident/hesitant', 'non_critical'),
    ('used_unprofessional_negative_expressions', 'Used unprofessional/negative expressions', 'non_critical'),
    ('didnt_verify_confirm_validate_data', "Didn't Verify/Confirm/Validate data", 'non_critical'),
    ('didnt_follow_transfer_hold_protocol', "Didn't follow Transfer / Hold protocol", 'non_critical'),
    ('wrong_greeting_closing_structure', 'Wrong greeting/closing structure', 'non_critical'),
    ('didnt_offer_extra_assistance', "Didn't offer extra assistance", 'non_critical'),
    ('delay_in_responding', 'Delay in responding', 'non_critical'),
    ('improper_greeting_closing_tone', 'Improper greeting / closing tone', 'non_critical'),
    ('no_greeting_closing_at_all', 'No greeting/closing at all', 'non_critical'),
]


def scorecard_items() -> list[dict]:
    """The scorecard items: one per mistake. "weight" is the points taken off when the mistake happens."""
    return [{"code": c, "name": n, "severity": s, "description": SEVERITY[s][0], "weight": SEVERITY[s][1],
             "critical": SEVERITY[s][2], "source": SOURCE} for c, n, s in ERRORS]


def apply_scoresheet(db) -> bool:
    """Switch ADIB to its own categories and scoresheet, once. Idempotent: does nothing after the first time, so
    later edits in Settings are kept. Returns True when it changed something."""
    from sqlalchemy import func

    from .models import Category, Enterprise, Scorecard
    if not db.get(Enterprise, "adib"):
        return False
    cards = db.query(Scorecard).filter_by(enterprise_id="adib").all()
    if any(any(k.get("source") == SOURCE for k in s.kpis) for s in cards):
        return False
    new = {c for c, _, _ in CATEGORIES}
    have = {c.code: c for c in db.query(Category).filter_by(enterprise_id="adib")}
    for code, cat in have.items():
        cat.active = code in new
    for code, name, group in CATEGORIES:
        if code not in have:
            db.add(Category(enterprise_id="adib", code=code, name=name, name_ar="", description=GROUPS[group]))
    last = db.query(func.max(Scorecard.version)).filter_by(enterprise_id="adib").scalar() or 0
    for s in cards:
        s.active = False
    db.add(Scorecard(enterprise_id="adib", version=last + 1, active=True, kpis=scorecard_items()))
    db.flush()
    return True
