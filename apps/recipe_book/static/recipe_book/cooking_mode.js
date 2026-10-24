const startButton = document.querySelector('#start-cooking-mode');
const mode = document.querySelector('#cooking-mode');

if (startButton && mode) {
  const stepList = document.querySelector('#full-cooking-steps');
  const steps = [...stepList.querySelectorAll('li')].map((step) => step.textContent.trim());
  const stepCount = document.querySelector('#cooking-step-count');
  const currentStep = document.querySelector('#cooking-current-step');
  const modeStatus = document.querySelector('#cooking-mode-status');
  const previousButton = document.querySelector('#previous-cooking-step');
  const nextButton = document.querySelector('#next-cooking-step');
  const exitButton = document.querySelector('#exit-cooking-mode');
  const checklist = document.querySelector('#cooking-ingredients');
  const minutesInput = document.querySelector('#step-timer-minutes');
  const timerButton = document.querySelector('#start-step-timer');
  const resetTimerButton = document.querySelector('#reset-step-timer');
  const timerDisplay = document.querySelector('#step-timer-display');
  const timerStatus = document.querySelector('#step-timer-status');
  let activeStep = 0;
  let remainingSeconds = 5 * 60;
  let timerDeadline = null;
  let timerInterval = null;

  const configuredSeconds = () => {
    const minutes = Number(minutesInput.value);
    return Number.isInteger(minutes) && minutes >= 1 && minutes <= 240 ? minutes * 60 : null;
  };

  function renderTimer() {
    const minutes = Math.floor(remainingSeconds / 60).toString().padStart(2, '0');
    const seconds = (remainingSeconds % 60).toString().padStart(2, '0');
    timerDisplay.textContent = `${minutes}:${seconds}`;
  }

  function stopTimer(reset = false) {
    if (timerInterval !== null) window.clearInterval(timerInterval);
    timerInterval = null;
    timerDeadline = null;
    timerButton.textContent = 'Mulai timer';
    if (reset) remainingSeconds = configuredSeconds() ?? 5 * 60;
    renderTimer();
  }

  function renderStep({focus = false} = {}) {
    stepCount.textContent = `Langkah ${activeStep + 1} dari ${steps.length}`;
    currentStep.textContent = steps[activeStep];
    previousButton.disabled = activeStep === 0;
    nextButton.disabled = false;
    nextButton.textContent = activeStep === steps.length - 1 ? 'Selesai' : 'Berikutnya';
    modeStatus.textContent = '';
    if (focus) currentStep.focus();
  }

  for (const [index, ingredient] of [...document.querySelectorAll('.ingredient-grid > li')].entries()) {
    const itemName = ingredient.querySelector('div')?.firstChild?.textContent.trim() || 'Bahan';
    const quantity = ingredient.querySelector('span')?.textContent.trim();
    const label = document.createElement('label');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = `cooking-ingredient-${index}`;
    const name = document.createElement('span');
    name.textContent = quantity ? `${itemName} · ${quantity}` : itemName;
    label.htmlFor = checkbox.id;
    label.append(checkbox, name);
    const row = document.createElement('li');
    row.append(label);
    checklist.append(row);
  }

  startButton.addEventListener('click', () => {
    stopTimer(true);
    activeStep = 0;
    renderStep();
    stepList.hidden = true;
    mode.hidden = false;
    currentStep.focus();
  });

  exitButton.addEventListener('click', () => {
    stopTimer();
    mode.hidden = true;
    stepList.hidden = false;
    startButton.focus();
  });

  previousButton.addEventListener('click', () => {
    if (activeStep === 0) return;
    stopTimer(true);
    timerStatus.textContent = 'Timer diatur ulang untuk langkah baru.';
    activeStep -= 1;
    renderStep({focus: true});
  });

  nextButton.addEventListener('click', () => {
    if (activeStep < steps.length - 1) {
      stopTimer(true);
      timerStatus.textContent = 'Timer diatur ulang untuk langkah baru.';
      activeStep += 1;
      renderStep({focus: true});
      return;
    }
    stopTimer();
    modeStatus.textContent = 'Panduan selesai. Jika sudah memasak, pilih “Sudah Masak” untuk mencatat pemakaian stok.';
    nextButton.disabled = true;
    currentStep.focus();
  });

  minutesInput.addEventListener('change', () => {
    const seconds = configuredSeconds();
    if (seconds === null) {
      minutesInput.setCustomValidity('Masukkan durasi 1 sampai 240 menit.');
      minutesInput.reportValidity();
      return;
    }
    minutesInput.setCustomValidity('');
    stopTimer(true);
    timerStatus.textContent = '';
  });

  timerButton.addEventListener('click', () => {
    if (timerInterval !== null) {
      remainingSeconds = Math.max(0, Math.ceil((timerDeadline - Date.now()) / 1000));
      stopTimer();
      timerStatus.textContent = 'Timer dijeda.';
      return;
    }
    if (remainingSeconds <= 0) remainingSeconds = configuredSeconds() ?? 5 * 60;
    if (configuredSeconds() === null) {
      minutesInput.setCustomValidity('Masukkan durasi 1 sampai 240 menit.');
      minutesInput.reportValidity();
      return;
    }
    minutesInput.setCustomValidity('');
    timerDeadline = Date.now() + remainingSeconds * 1000;
    timerButton.textContent = 'Jeda timer';
    timerStatus.textContent = 'Timer berjalan.';
    timerInterval = window.setInterval(() => {
      remainingSeconds = Math.max(0, Math.ceil((timerDeadline - Date.now()) / 1000));
      renderTimer();
      if (remainingSeconds === 0) {
        stopTimer();
        timerStatus.textContent = 'Timer selesai.';
      }
    }, 250);
  });

  resetTimerButton.addEventListener('click', () => {
    stopTimer(true);
    timerStatus.textContent = 'Timer diatur ulang.';
  });

  renderTimer();
}
