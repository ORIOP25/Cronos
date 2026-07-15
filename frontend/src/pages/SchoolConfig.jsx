import React, { useState } from 'react'
import {
  CAlert,
  CBadge,
  CCard,
  CCardBody,
  CCardHeader,
  CTab,
  CTabContent,
  CTabList,
  CTabPanel,
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
  { key: 'settings', label: 'Período Letivo', heading: 'Definição do Período Letivo', component: SettingsSection },
  { key: 'calendar', label: 'Calendário e Interrupções', heading: 'Calendário (Feriados e Pausas)', component: CalendarSection },
  { key: 'grid', label: 'Grelha Horária', heading: 'Definição da Grelha Horária', component: GridSection },
]

const SchoolConfig = () => {
  const { organization } = useOrganization()
  const [activeTab, setActiveTab] = useState('settings')

  return (
    <div className="p-4">
      <PageHeader preTitle="Configuração" title="Escola" />
      {organization?.name && (
        <CAlert color="primary" className="d-flex align-items-center gap-2 py-2 mb-4">
          A gerir organização:
          <CBadge color="light" textColor="primary" className="fs-6">
            {organization.name}
          </CBadge>
        </CAlert>
      )}
      <CTabs activeItemKey={activeTab} onChange={setActiveTab}>
        <CTabList variant="tabs" className="mb-4">
          {TAB_DEFINITIONS.map((tab) => (
            <CTab key={tab.key} itemKey={tab.key}>{tab.label}</CTab>
          ))}
        </CTabList>
        <CTabContent>
          {TAB_DEFINITIONS.map((tab) => (
            <CTabPanel key={tab.key} itemKey={tab.key}>
              <CCard className="border-0 shadow-sm">
                <CCardHeader className="bg-white fw-bold py-3">{tab.heading}</CCardHeader>
                <CCardBody className="p-4">{React.createElement(tab.component)}</CCardBody>
              </CCard>
            </CTabPanel>
          ))}
        </CTabContent>
      </CTabs>
    </div>
  )
}

export default SchoolConfig
