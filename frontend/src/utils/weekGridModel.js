import { addDays, normalizeTimeLabel } from './formatUtils'

export function buildWeekGridModel(slots = [], baseTimeslots = [], weekStart = '') {
  const referenceTimeslots = baseTimeslots.length > 0
    ? baseTimeslots
    : slots.map((slot) => slot.timeslot).filter(Boolean)
  const uniqueTimes = [...new Set(referenceTimeslots.map((timeslot) => normalizeTimeLabel(timeslot.start_time)))]
    .sort((left, right) => left.localeCompare(right))
  const activeDays = [...new Set(referenceTimeslots.map((timeslot) => timeslot.day_of_week))]
    .sort((left, right) => left - right)
  const endTimeMap = Object.fromEntries(referenceTimeslots.map((timeslot) => [
    normalizeTimeLabel(timeslot.start_time),
    normalizeTimeLabel(timeslot.end_time),
  ]))
  const datesFromSlots = Object.fromEntries(slots
    .filter((slot) => slot.timeslot && slot.date)
    .map((slot) => [slot.timeslot.day_of_week, slot.date]))
  const dayDateMap = Object.fromEntries(activeDays.map((day) => [
    day,
    datesFromSlots[day] ?? (weekStart ? addDays(weekStart, day) : ''),
  ]))
  const slotMap = {}
  slots.forEach((slot) => {
    const key = `${slot.timeslot.day_of_week}:${normalizeTimeLabel(slot.timeslot.start_time)}`
    slotMap[key] ??= []
    slotMap[key].push(slot)
  })
  return { slotMap, uniqueTimes, activeDays, endTimeMap, dayDateMap }
}
