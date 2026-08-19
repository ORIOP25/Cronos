import { useEffect, useMemo, useRef, useState } from 'react'
import { PREFERENCE_LEVELS, DEFAULT_PREFERENCE } from '../constants'

const DAY_LABELS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']

function timeLabel(time = '') { return time.slice(0, 5) }

export default function AvailabilityGrid({ timeslots = [], availabilityMap, onChange, selectedMode }) {
  const [focusedId, setFocusedId] = useState(null)
  const paintSession = useRef({ active: false, lastPaintedId: null })
  const cellRefs = useRef(new Map())

  const model = useMemo(() => {
    const slotByKey = new Map(timeslots.map((slot) => [`${slot.day_of_week}:${timeLabel(slot.start_time)}`, slot]))
    const days = [...new Set(timeslots.map((slot) => slot.day_of_week))].sort((a, b) => a - b)
    const times = [...new Set(timeslots.map((slot) => timeLabel(slot.start_time)))].sort((a, b) => a.localeCompare(b))
    return { slotByKey, days, times }
  }, [timeslots])

  const effectiveFocusedId = timeslots.some((slot) => slot.id === focusedId) ? focusedId : timeslots[0]?.id ?? null

  const getScore = (id) => availabilityMap[id] ?? DEFAULT_PREFERENCE
  const applyPaint = (slot) => {
    if (!slot || paintSession.current.lastPaintedId === slot.id) return
    paintSession.current.lastPaintedId = slot.id
    if (getScore(slot.id) !== selectedMode) onChange(slot.id, selectedMode)
  }

  useEffect(() => {
    const endPaint = () => { paintSession.current.active = false; paintSession.current.lastPaintedId = null }
    window.addEventListener('pointerup', endPaint)
    window.addEventListener('pointercancel', endPaint)
    window.addEventListener('blur', endPaint)
    return () => {
      window.removeEventListener('pointerup', endPaint)
      window.removeEventListener('pointercancel', endPaint)
      window.removeEventListener('blur', endPaint)
    }
  }, [])

  const moveFocus = (currentSlot, dayOffset, timeOffset) => {
    const dayIndex = model.days.indexOf(currentSlot.day_of_week)
    const timeIndex = model.times.indexOf(timeLabel(currentSlot.start_time))
    const nextDay = model.days[dayIndex + dayOffset]
    const nextTime = model.times[timeIndex + timeOffset]
    if (nextDay === undefined || nextTime === undefined) return
    const next = model.slotByKey.get(`${nextDay}:${nextTime}`)
    if (next) {
      setFocusedId(next.id)
      cellRefs.current.get(next.id)?.focus()
    }
  }

  const handleKeyDown = (event, slot) => {
    const moves = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] }
    if (moves[event.key]) {
      event.preventDefault()
      moveFocus(slot, moves[event.key][0], moves[event.key][1])
      return
    }
    if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      const time = timeLabel(slot.start_time)
      const day = event.key === 'Home' ? model.days[0] : model.days.at(-1)
      const next = model.slotByKey.get(`${day}:${time}`)
      if (next) {
        setFocusedId(next.id)
        cellRefs.current.get(next.id)?.focus()
      }
      return
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      applyPaint(slot)
    }
  }

  return (
    <div className="availability-grid-scroll" role="region" aria-label="Grelha de preferências de disponibilidade" tabIndex="0">
      <div className="availability-grid" style={{ '--availability-days': model.days.length }}>
        <div className="availability-grid__header">Hora</div>
        {model.days.map((day) => <div className="availability-grid__header" key={day}>{DAY_LABELS[day] ?? `Dia ${day + 1}`}</div>)}
        {model.times.map((time) => (
          <div className="availability-grid__row" key={time}>
            <div className="availability-grid__time">{time}</div>
            {model.days.map((day) => {
              const slot = model.slotByKey.get(`${day}:${time}`)
              if (!slot) return <div className="availability-grid__empty" key={`${day}-${time}`} aria-label="Bloco indisponível">—</div>
              const score = getScore(slot.id)
              const preference = PREFERENCE_LEVELS[score]
              const selected = effectiveFocusedId === slot.id
              return (
                <button
                  type="button"
                  key={slot.id}
                  ref={(element) => {
                    if (element) cellRefs.current.set(slot.id, element)
                    else cellRefs.current.delete(slot.id)
                  }}
                  data-timeslot-id={slot.id}
                  className="availability-grid__cell"
                  style={{ '--preference-color': preference.color }}
                  tabIndex={selected ? 0 : -1}
                  aria-label={`${DAY_LABELS[day] ?? `Dia ${day + 1}`}, ${time}, estado guardado: ${preference.label}, ferramenta ativa: ${PREFERENCE_LEVELS[selectedMode].label}`}
                  onFocus={() => setFocusedId(slot.id)}
                  onKeyDown={(event) => handleKeyDown(event, slot)}
                  onPointerDown={(event) => {
                    if (event.button !== 0) return
                    event.preventDefault()
                    event.currentTarget.setPointerCapture?.(event.pointerId)
                    paintSession.current.active = true
                    paintSession.current.lastPaintedId = null
                    applyPaint(slot)
                  }}
                  onPointerEnter={() => { if (paintSession.current.active) applyPaint(slot) }}
                  onPointerUp={() => { paintSession.current.active = false; paintSession.current.lastPaintedId = null }}
                >
                  {preference.label}
                </button>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
