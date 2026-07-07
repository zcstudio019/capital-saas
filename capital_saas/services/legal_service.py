from sqlalchemy.orm import Session

from db.models import LegalAcceptance,LegalDocument

DEFAULT_LEGAL=[
 ("privacy_policy","隐私政策","平台仅在融资诊断、顾问服务和项目交付所需范围内处理企业及联系人数据。"),
 ("user_agreement","用户服务协议","用户应保证提交信息真实、合法，并理解系统输出不构成授信承诺。"),
 ("financing_service_disclaimer","融资服务免责声明","实际融资结果以银行及金融机构审批为准。"),
 ("data_authorization","数据处理授权说明","用户授权平台为融资规划、资料核验和服务交付处理已提交数据。"),
 ("document_submission_authorization","资料提交授权","经客户明确确认后，顾问可将指定资料提交给拟申请金融机构。"),
]
def ensure_default_legal_documents(db:Session):
    existing={x[0] for x in db.query(LegalDocument.document_key).all()}
    for key,title,content in DEFAULT_LEGAL:
        if key not in existing:db.add(LegalDocument(document_key=key,title=title,content=content,version="1.0",is_active=True))
    db.commit()
def missing_acceptances(db,customer,keys):
    docs=db.query(LegalDocument).filter(LegalDocument.is_active.is_(True),LegalDocument.document_key.in_(keys)).all()
    accepted={(x.document_key,x.document_version) for x in db.query(LegalAcceptance).filter_by(customer_id=customer.id).all()}
    return [x for x in docs if (x.document_key,x.version) not in accepted]
