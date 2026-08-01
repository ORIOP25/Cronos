import { memo } from 'react'
import { testimonials } from '../../data/marketingData'

const row1 = [...testimonials.slice(0, 3), ...testimonials.slice(0, 3)]
const row2 = [...testimonials.slice(3, 6), ...testimonials.slice(3, 6)]

const TestimonialsMarquee = memo(function TestimonialsMarquee() {
  return (
    <section className="cronos-testimonials" id="testemunhos" aria-labelledby="cronos-testimonials-title">
      <div className="cronos-layout">
        <div className="cronos-testimonials__heading">
          <h2 id="cronos-testimonials-title">
            Histórias de quem confia no Cronos
          </h2>
        </div>
      </div>

      <div className="cronos-testimonials-marquee">
        {/* Row 1: Looping Right */}
        <div className="cronos-marquee-row cronos-marquee-row--right">
          {row1.map((item, idx) => (
            <article className="cronos-testimonial-card" key={`r1-${item.name}-${idx}`}>
              <div className="cronos-testimonial-card__quote-mark">“</div>
              <blockquote className="cronos-testimonial-card__quote">{item.quote}</blockquote>
              <div className="cronos-testimonial-card__author">
                <div className="cronos-avatar" aria-hidden="true">{item.avatar}</div>
                <div className="cronos-testimonial-card__author-info">
                  <h3>{item.name}</h3>
                  <p className="cronos-testimonial-card__role">{item.role}</p>
                </div>
              </div>
            </article>
          ))}
        </div>

        {/* Row 2: Looping Left */}
        <div className="cronos-marquee-row cronos-marquee-row--left">
          {row2.map((item, idx) => (
            <article className="cronos-testimonial-card" key={`r2-${item.name}-${idx}`}>
              <div className="cronos-testimonial-card__quote-mark">“</div>
              <blockquote className="cronos-testimonial-card__quote">{item.quote}</blockquote>
              <div className="cronos-testimonial-card__author">
                <div className="cronos-avatar" aria-hidden="true">{item.avatar}</div>
                <div className="cronos-testimonial-card__author-info">
                  <h3>{item.name}</h3>
                  <p className="cronos-testimonial-card__role">{item.role}</p>
                </div>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
})

export default TestimonialsMarquee
