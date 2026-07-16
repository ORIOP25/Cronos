import { CBadge } from '@coreui/react'
import { getRoomType } from '../utils/presentation'

const RoomTypeBadge = ({ type }) => {
  const metadata = getRoomType(type)
  return <CBadge color={metadata.color} shape="rounded-pill" className={metadata.textClass}>{metadata.label}</CBadge>
}

export default RoomTypeBadge
