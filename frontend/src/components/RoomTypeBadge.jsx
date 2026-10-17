import { CBadge } from '@coreui/react'

const RoomTypeBadge = ({ roomType }) => {
  return <CBadge color="secondary" shape="rounded-pill">{roomType?.name || '—'}</CBadge>
}

export default RoomTypeBadge
