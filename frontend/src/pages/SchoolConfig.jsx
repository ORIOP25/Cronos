import { useState } from 'react'
import {
  CCard,
  CCardBody,
  CCardHeader,
  CTab,
  CTabList,
  CTabs,
} from '@coreui/react'
import { useOrganization } from '@clerk/react'
import PageHeader from '../components/PageHeader'
import {
  CalendarSection,
  GridSection,
  SettingsSection,
} from '../features/schoolConfig/SchoolConfigSections'

const TAB_DEFINITIONS = [
  { key: 'settings', label: 'Período letivo', heading: 'Definição do período letivo', component: SettingsSection },
  { key: 'calendar', label: 'Calendário e interrupções', heading: 'Calendário e interrupções', component: CalendarSection },
  { key: 'grid', label: 'Grelha horária', heading: 'Definição da grelha horária', component: GridSection },
]

const SchoolConfig = () => {
  const { organization } = useOrganization()
  const [activeTab, setActiveTab] = useState('settings')
  const activeSection = TAB_DEFINITIONS.find((tab) => tab.key === activeTab) ?? TAB_DEFINITIONS[0]
  const ActiveSection = activeSection.component

  return (
    <div>
      <PageHeader preTitle="Configuração" title="Escola" context={organization?.name ? `Organização: ${organization.name}` : undefined} />
      <CTabs activeItemKey={activeTab} onChange={setActiveTab}>
        <CTabList variant="tabs" className="mb-4">
          {TAB_DEFINITIONS.map((tab) => (
            <CTab key={tab.key} itemKey={tab.key}>{tab.label}</CTab>
          ))}
        </CTabList>
        <CCard className="border-0 shadow-sm">
          <CCardHeader className="bg-white fw-bold py-3">{activeSection.heading}</CCardHeader>
          <CCardBody className="p-4"><ActiveSection /></CCardBody>
        </CCard>
      </CTabs>
    </div>
  )
}

export default SchoolConfig
