import { describe, expect, it } from 'vitest'
import { publicIdentity } from '../features/marketing/content/publicIdentity'

describe('public identity', () => {
  it('keeps the approved public identity in one frozen source', () => {
    expect(publicIdentity).toMatchObject({
      brand: 'Cronos',
      descriptor: 'Gestão de Horários para o Ensino Profissional em Portugal',
      email: 'contacto@cronos.pt',
      address: {
        street: 'R. dos Combatentes do Ultramar',
        postalCode: '2715-311',
        locality: 'Pêro Pinheiro',
        country: 'PT',
      },
    })
    expect(Object.isFrozen(publicIdentity)).toBe(true)
    expect(Object.isFrozen(publicIdentity.address)).toBe(true)
    expect('phone' in publicIdentity).toBe(false)
    expect('telephone' in publicIdentity).toBe(false)
  })
})
