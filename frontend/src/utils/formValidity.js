/**
 * Validação nativa com mensagens em português.
 * Usar em campos `required`/numéricos para substituir a mensagem do browser.
 */

export function applyPortugueseValidity(event) {
  const input = event.currentTarget
  const { validity } = input
  if (validity.valueMissing) {
    input.setCustomValidity('Preencha este campo.')
  } else if (validity.rangeUnderflow || validity.rangeOverflow) {
    input.setCustomValidity('Indique um valor dentro do intervalo permitido.')
  } else if (
    validity.typeMismatch
    || validity.badInput
    || validity.patternMismatch
    || validity.stepMismatch
  ) {
    input.setCustomValidity('Indique um valor válido.')
  } else {
    input.setCustomValidity('')
  }
  input.setAttribute('aria-invalid', 'true')
}

export function clearPortugueseValidity(event) {
  event.currentTarget.setCustomValidity('')
  event.currentTarget.removeAttribute('aria-invalid')
}

/** Props prontas para espalhar em campos nativos com validação. */
export const portugueseValidityProps = {
  onInvalid: applyPortugueseValidity,
  onInput: clearPortugueseValidity,
}
