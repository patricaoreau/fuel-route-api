import * as maplibregl from "https://unpkg.com/maplibre-gl@6.11.2/dist/maplibre-gl.mjs";

(() => {
  "use strict";

  const endpoint = window.FUEL_ROUTE_CONFIG.endpoint;
  const suggestionsEndpoint = window.FUEL_ROUTE_CONFIG.suggestionsEndpoint;
  const form = document.querySelector("#route-form");
  const startInput = document.querySelector("#start-location");
  const finishInput = document.querySelector("#finish-location");
  const submitButton = document.querySelector("#submit-route");
  const resultsPane = document.querySelector(".results-pane");
  const results = document.querySelector("#results");
  const emptyResults = document.querySelector("#empty-results");
  const loadingState = document.querySelector("#loading-state");
  const mapState = document.querySelector("#map-state");
  const routeBadge = document.querySelector("#route-badge");
  const errorBanner = document.querySelector("#error-banner");
  const errorMessage = document.querySelector("#error-message");
  const rawResponse = document.querySelector("#raw-response");

  let responseData = null;
  let activeRequest = null;
  let mapMarkers = [];

  const map = new maplibregl.Map({
    container: "map",
    style: "https://tiles.openfreemap.org/styles/liberty",
    center: [-98.35, 39.5],
    zoom: 3.4,
    attributionControl: true,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
  const mapReady = new Promise((resolve) => map.on("load", resolve));

  const formatMoney = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  });

  const formatNumber = new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 1,
  });

  const formatGallons = new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 2,
  });

  function setLoading(isLoading) {
    submitButton.disabled = isLoading;
    submitButton.querySelector("span").textContent = isLoading ? "Running" : "Run route";
    loadingState.hidden = !isLoading;
    resultsPane.setAttribute("aria-busy", String(isLoading));
  }

  function showError(error) {
    const fields = error.fields ? Object.values(error.fields).join(" ") : "";
    errorMessage.textContent = fields || error.message || "The request could not be completed.";
    errorBanner.hidden = false;
  }

  function clearError() {
    errorBanner.hidden = true;
    errorMessage.textContent = "";
  }

  function attachAutocomplete(input, list) {
    let debounceTimer;
    let requestController;
    let suggestions = [];
    let activeIndex = -1;

    function close() {
      list.hidden = true;
      list.replaceChildren();
      suggestions = [];
      activeIndex = -1;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    }

    function setActive(index) {
      const options = [...list.querySelectorAll(".suggestion-option")];
      options.forEach((option, optionIndex) => {
        const isActive = optionIndex === index;
        option.classList.toggle("is-active", isActive);
        option.setAttribute("aria-selected", String(isActive));
      });
      activeIndex = index;
      if (options[index]) {
        input.setAttribute("aria-activedescendant", options[index].id);
        options[index].scrollIntoView({ block: "nearest" });
      }
    }

    function choose(index) {
      const suggestion = suggestions[index];
      if (!suggestion) {
        return;
      }
      input.value = suggestion.label;
      close();
      clearError();
    }

    function render(items) {
      suggestions = items;
      activeIndex = -1;
      list.replaceChildren();
      if (!items.length) {
        close();
        return;
      }
      items.forEach((suggestion, index) => {
        const option = document.createElement("li");
        option.id = `${list.id}-option-${index}`;
        option.className = "suggestion-option";
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", "false");
        appendText(option, "strong", suggestion.label);
        appendText(option, "span", suggestion.state_name);
        option.addEventListener("pointerdown", (event) => event.preventDefault());
        option.addEventListener("click", () => choose(index));
        list.appendChild(option);
      });
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }

    async function loadSuggestions() {
      const query = input.value.trim();
      if (query.length < 2) {
        close();
        return;
      }
      const comparisonQuery = query.toLocaleLowerCase("en-US");
      if (requestController) {
        requestController.abort();
      }
      requestController = new AbortController();
      try {
        const response = await fetch(
          `${suggestionsEndpoint}?q=${encodeURIComponent(comparisonQuery)}`,
          { signal: requestController.signal }
        );
        if (!response.ok) {
          close();
          return;
        }
        const payload = await response.json();
        render(payload.suggestions || []);
      } catch (error) {
        if (error.name !== "AbortError") {
          close();
        }
      }
    }

    input.addEventListener("input", () => {
      window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(loadSuggestions, 180);
    });
    input.addEventListener("keydown", (event) => {
      if (list.hidden || !suggestions.length) {
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActive((activeIndex + 1) % suggestions.length);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActive((activeIndex - 1 + suggestions.length) % suggestions.length);
      } else if (event.key === "Enter" && activeIndex >= 0) {
        event.preventDefault();
        choose(activeIndex);
      } else if (event.key === "Escape") {
        close();
      }
    });
    input.addEventListener("blur", () => {
      window.setTimeout(close, 100);
    });
    input.addEventListener("focus", () => {
      if (suggestions.length) {
        list.hidden = false;
        input.setAttribute("aria-expanded", "true");
      }
    });

    return close;
  }

  function clearMapLayers() {
    mapMarkers.forEach((marker) => marker.remove());
    mapMarkers = [];
    if (map.getLayer("fuel-route")) {
      map.removeLayer("fuel-route");
    }
    if (map.getSource("fuel-route")) {
      map.removeSource("fuel-route");
    }
  }

  function popupNode(title, detail) {
    const node = document.createElement("div");
    node.className = "map-popup";
    const strong = document.createElement("strong");
    const span = document.createElement("span");
    strong.textContent = title;
    span.textContent = detail;
    node.append(strong, span);
    return node;
  }

  async function renderMap(data) {
    await mapReady;
    clearMapLayers();
    mapState.hidden = true;
    routeBadge.hidden = false;
    document.querySelector("#route-label").textContent = `${data.start.label} to ${data.finish.label}`;

    map.addSource("fuel-route", {
      type: "geojson",
      data: {
        type: "Feature",
        properties: {},
        geometry: data.route.geometry,
      },
    });
    map.addLayer({
      id: "fuel-route",
      type: "line",
      source: "fuel-route",
      layout: {
        "line-cap": "round",
        "line-join": "round",
      },
      paint: {
        "line-color": "#16734a",
        "line-width": 5,
        "line-opacity": 0.92,
      },
    });

    const startMarker = new maplibregl.Marker({ color: "#16734a" })
      .setLngLat(data.start.coordinates)
      .setPopup(new maplibregl.Popup({ offset: 22 }).setDOMContent(popupNode("Start", data.start.label)))
      .addTo(map);
    const finishMarker = new maplibregl.Marker({ color: "#18211c" })
      .setLngLat(data.finish.coordinates)
      .setPopup(new maplibregl.Popup({ offset: 22 }).setDOMContent(popupNode("Finish", data.finish.label)))
      .addTo(map);
    mapMarkers.push(startMarker, finishMarker);

    data.fuel_stops.forEach((stop, index) => {
      const marker = new maplibregl.Marker({ color: "#b56214", scale: 0.72 })
        .setLngLat(stop.coordinates)
        .setPopup(new maplibregl.Popup({ offset: 18 }).setDOMContent(popupNode(
          `${index + 1}. ${stop.name}`,
          `${formatMoney.format(stop.price_per_gallon)}/gal · ${formatGallons.format(stop.gallons)} gal`
        )))
        .addTo(map);
      mapMarkers.push(marker);
    });

    const bounds = new maplibregl.LngLatBounds();
    data.route.geometry.coordinates.forEach((coordinate) => bounds.extend(coordinate));
    map.fitBounds(bounds, { padding: 48, maxZoom: 10, duration: 0 });
  }

  function appendText(parent, tagName, text, className) {
    const element = document.createElement(tagName);
    element.textContent = text;
    if (className) {
      element.className = className;
    }
    parent.appendChild(element);
    return element;
  }

  function renderStops(stops) {
    const list = document.querySelector("#stop-list");
    list.replaceChildren();

    stops.forEach((stop, index) => {
      const item = document.createElement("li");
      item.className = "stop-item";
      appendText(item, "span", String(index + 1), "stop-number");

      const main = document.createElement("div");
      main.className = "stop-main";
      appendText(main, "strong", stop.name);
      appendText(
        main,
        "span",
        `${stop.city}, ${stop.state} · mile ${formatNumber.format(stop.route_mile)} · ${formatMoney.format(stop.price_per_gallon)}/gal`
      );

      const cost = document.createElement("div");
      cost.className = "stop-cost";
      appendText(cost, "strong", formatMoney.format(stop.cost));
      appendText(cost, "span", `${formatGallons.format(stop.gallons)} gal`);
      item.append(main, cost);
      list.appendChild(item);
    });
  }

  async function renderResults(data) {
    responseData = data;
    emptyResults.hidden = true;
    results.hidden = false;
    document.querySelector("#result-title").textContent = `${data.start.label} to ${data.finish.label}`;
    document.querySelector("#total-cost").textContent = formatMoney.format(data.total_fuel_cost);
    document.querySelector("#distance").textContent = `${formatNumber.format(data.route.distance_miles)} mi`;
    document.querySelector("#duration").textContent = `${formatNumber.format(data.route.duration_hours)} hr`;
    document.querySelector("#gallons").textContent = `${formatNumber.format(data.total_gallons)} gal`;
    document.querySelector("#stop-count").textContent = String(data.fuel_stops.length);
    document.querySelector("#vehicle-spec").textContent = `${data.vehicle.mpg} MPG · ${data.vehicle.max_range_miles} mi range`;
    rawResponse.textContent = JSON.stringify(data, null, 2);
    renderStops(data.fuel_stops);
    await renderMap(data);
  }

  async function submitRoute(event) {
    event.preventDefault();
    clearError();

    if (activeRequest) {
      activeRequest.abort();
    }
    activeRequest = new AbortController();
    setLoading(true);

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start: startInput.value.trim(),
          finish: finishInput.value.trim(),
        }),
        signal: activeRequest.signal,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw payload.error || { message: `Request failed with HTTP ${response.status}.` };
      }
      await renderResults(payload);
    } catch (error) {
      if (error.name !== "AbortError") {
        showError(error);
      }
    } finally {
      setLoading(false);
      activeRequest = null;
    }
  }

  const closeStartSuggestions = attachAutocomplete(
    startInput,
    document.querySelector("#start-suggestions")
  );
  const closeFinishSuggestions = attachAutocomplete(
    finishInput,
    document.querySelector("#finish-suggestions")
  );

  form.addEventListener("submit", (event) => {
    closeStartSuggestions();
    closeFinishSuggestions();
    submitRoute(event);
  });

  document.querySelector("#swap-locations").addEventListener("click", () => {
    const previousStart = startInput.value;
    startInput.value = finishInput.value;
    finishInput.value = previousStart;
    closeStartSuggestions();
    closeFinishSuggestions();
    startInput.focus();
  });

  document.querySelector("#dismiss-error").addEventListener("click", clearError);

  document.querySelector("#copy-response").addEventListener("click", async (event) => {
    if (!responseData) {
      return;
    }
    const button = event.currentTarget;
    try {
      await navigator.clipboard.writeText(JSON.stringify(responseData, null, 2));
      button.title = "Copied";
      window.setTimeout(() => { button.title = "Copy response"; }, 1400);
    } catch (error) {
      showError({ message: "The browser could not copy the response." });
    }
  });

  let resizeTimer;
  window.addEventListener("resize", () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => {
      map.resize();
      if (responseData) {
        const bounds = new maplibregl.LngLatBounds();
        responseData.route.geometry.coordinates.forEach((coordinate) => bounds.extend(coordinate));
        map.fitBounds(bounds, { padding: 48, maxZoom: 10, duration: 0 });
      }
    }, 120);
  });

  lucide.createIcons({ attrs: { "stroke-width": 1.8 } });
})();
