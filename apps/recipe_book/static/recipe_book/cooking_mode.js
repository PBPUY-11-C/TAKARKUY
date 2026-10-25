import {clearCookingProgress, restoreCookingProgress, saveCookingProgress} from './cooking_progress.mjs';

const startButton = document.querySelector('#start-cooking-mode');
const mode = document.querySelector('#cooking-mode');

if (startButton && mode) {
  const recipeDetail = document.querySelector('#recipe-detail');
  const stepList = document.querySelector('#full-cooking-steps');
  const steps = [...stepList.querySelectorAll('li')].map((step) => step.textContent.trim());
  const stepCount = document.querySelector('#cooking-step-count');
  const currentStep = document.querySelector('#cooking-current-step');
  const modeStatus = document.querySelector('#cooking-mode-status');
  const previousButton = document.querySelector('#previous-cooking-step');
  const nextButton = document.querySelector('#next-cooking-step');
  const exitButton = document.querySelector('#exit-cooking-mode');
  const restartButton = document.querySelector('#reset-cooking-progress');
  const checklist = document.querySelector('#cooking-ingredients');
  const minutesInput = document.querySelector('#step-timer-minutes');
  const timerButton = document.querySelector('#start-step-timer');
  const resetTimerButton = document.querySelector('#reset-step-timer');
  const timerDisplay = document.querySelector('#step-timer-display');
  const timerStatus = document.querySelector('#step-timer-status');
  let storage = null;
  try { storage = window.sessionStorage; } catch { /* Cooking mode remains usable without session storage. */ }
  const progressKey = `takarkuy:cooking-progress:${recipeDetail.dataset.code}:${recipeDetail.dataset.servings}`;
  const checkboxes = [];
  const ingredientFingerprint = [];
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
    modeStatus.textContent = `Langkah ${activeStep + 1} dari ${steps.length}.`;
    if (focus) currentStep.focus();
  }

  function saveProgress() {
    saveCookingProgress(
      storage,
      progressKey,
      activeStep,
      checkboxes.map((checkbox) => checkbox.checked),
      JSON.stringify({steps, ingredients: ingredientFingerprint}),
    );
  }

  for (const [index, ingredient] of [...document.querySelectorAll('.ingredient-grid > li')].entries()) {
    const itemName = ingredient.querySelector('div')?.firstChild?.textContent.trim() || 'Bahan';
    const quantity = ingredient.querySelector('span')?.textContent.trim();
    ingredientFingerprint.push([itemName, quantity || '']);
    const label = document.createElement('label');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = `cooking-ingredient-${index}`;
    checkboxes.push(checkbox);
    const name = document.createElement('span');
    name.textContent = quantity ? `${itemName} · ${quantity}` : itemName;
    label.htmlFor = checkbox.id;
    label.append(checkbox, name);
    const row = document.createElement('li');
    row.append(label);
    checklist.append(row);
    checkbox.addEventListener('change', saveProgress);
  }

  startButton.addEventListener('click', () => {
    stopTimer(true);
    const progress = restoreCookingProgress(
      storage,
      progressKey,
      steps.length,
      checkboxes.length,
      JSON.stringify({steps, ingredients: ingredientFingerprint}),
    );
    activeStep = progress?.step ?? 0;
    checkboxes.forEach((checkbox, index) => { checkbox.checked = progress?.checked[index] ?? false; });
    renderStep();
    modeStatus.textContent = progress
      ? `Langkah dan checklist dipulihkan. Langkah ${activeStep + 1} dari ${steps.length}. Mulai ulang timer untuk langkah ini.`
      : `Mode memasak dimulai. Langkah ${activeStep + 1} dari ${steps.length}.`;
    stepList.hidden = true;
    mode.hidden = false;
    startButton.setAttribute('aria-expanded', 'true');
    currentStep.focus();
  });

  exitButton.addEventListener('click', () => {
    stopTimer();
    mode.hidden = true;
    stepList.hidden = false;
    startButton.setAttribute('aria-expanded', 'false');
    saveProgress();
    startButton.focus();
  });

  restartButton.addEventListener('click', () => {
    stopTimer(true);
    clearCookingProgress(storage, progressKey);
    activeStep = 0;
    checkboxes.forEach((checkbox) => { checkbox.checked = false; });
    timerStatus.textContent = '';
    renderStep({focus: true});
    modeStatus.textContent = 'Progres mode memasak diatur ulang.';
  });

  previousButton.addEventListener('click', () => {
    if (activeStep === 0) return;
    stopTimer(true);
    timerStatus.textContent = 'Timer diatur ulang untuk langkah baru.';
    activeStep -= 1;
    renderStep({focus: true});
    saveProgress();
  });

  nextButton.addEventListener('click', () => {
    if (activeStep < steps.length - 1) {
      stopTimer(true);
      timerStatus.textContent = 'Timer diatur ulang untuk langkah baru.';
      activeStep += 1;
      renderStep({focus: true});
      saveProgress();
      return;
    }
    stopTimer();
    clearCookingProgress(storage, progressKey);
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
