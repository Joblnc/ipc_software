const lightButton = document.getElementById("lightButton");
const estimateButton = document.getElementById("estimateButton");
const lightStateText = document.getElementById("lightStateText");
const estimateStateText = document.getElementById("estimateStateText");
const resultText = document.getElementById("resultText");

let isLightOn = false;

function setLightUi(nextState) {
  isLightOn = nextState;
  lightButton.textContent = isLightOn ? "Eteindre la lumiere" : "Allumer la lumiere";
  lightButton.setAttribute("aria-pressed", String(isLightOn));
  lightStateText.textContent = isLightOn ? "Allumee" : "Eteinte";
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Erreur serveur");
  }

  return response.json();
}

async function handleLightClick() {
  const nextState = !isLightOn;
  setLightUi(nextState);

  try {
    await postJson("/api/light", { is_on: nextState });
    resultText.textContent = nextState
      ? "Lumiere allumee. Le frontend est pret a envoyer la commande au backend."
      : "Lumiere eteinte. Le frontend est pret a envoyer la commande au backend.";
  } catch (error) {
    resultText.textContent = "Mode autonome: la bascule visuelle fonctionne, mais le backend n'est pas encore branche.";
  }
}

async function handleEstimateClick() {
  estimateButton.disabled = true;
  estimateStateText.textContent = "En cours...";
  resultText.textContent = "Demande d'estimation en cours.";

  try {
    const response = await postJson("/api/estimate", {
      light_on: isLightOn,
      timestamp: new Date().toISOString(),
    });

    estimateStateText.textContent = "Calculee";
    resultText.textContent = response.message || "Estimation recuperee depuis le backend.";
  } catch (error) {
    estimateStateText.textContent = "Simulee";
    resultText.textContent = "Estimation a brancher sur le backend: remplace la logique de simulation par ton modele ou ta regle metier.";
  } finally {
    estimateButton.disabled = false;
  }
}

lightButton.addEventListener("click", handleLightClick);
estimateButton.addEventListener("click", handleEstimateClick);

setLightUi(false);