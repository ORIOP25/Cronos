import legalContent from './legal-content.json'
import LegalText from './LegalText.jsx'

export const LEGAL_EFFECTIVE_DATE = legalContent.effective_date

export const documents = Object.fromEntries(
  Object.entries(legalContent.documents).map(([kind, document]) => [
    kind,
    {
      ...document,
      sections: document.sections.map(({ title, body }) => [
        title,
        <LegalText key={`${kind}-${title}`} text={body} />,
      ]),
    },
  ]),
)
