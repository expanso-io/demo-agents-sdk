(function () {
  "use strict";

  var data = JSON.parse(document.getElementById("explorer-data").textContent);
  var state = { path: 0, ticket: 0, stage: 0 };
  var timers = new WeakMap();
  var root = document.documentElement;

  function $(id) {
    return document.getElementById(id);
  }

  /* Every stage input and output in the contract is a JSON object. */
  function pretty(value) {
    return JSON.stringify(value, null, 2);
  }

  function currentPath() {
    return data.paths[state.path];
  }

  function currentTicket() {
    return data.tickets[state.ticket];
  }

  function currentStage() {
    return currentPath().stages[state.stage];
  }

  function currentIo() {
    return currentStage().io[currentTicket().id];
  }

  /* Feedback lands in the status text beside the control that was used. */
  function report(control, ok, message) {
    var line = control.closest(".copy-line");
    var status = line && line.querySelector(".status");

    if (!status) {
      return;
    }

    status.textContent = message;
    status.className = "status " + (ok ? "ok" : "fail");
    clearTimeout(timers.get(status));
    timers.set(
      status,
      setTimeout(function () {
        status.textContent = "";
        status.className = "status";
      }, ok ? 3000 : 8000)
    );
  }

  function copyWithSelection(text) {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "0";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    var ok = false;

    try {
      ok = document.execCommand("copy");
    } catch (error) {
      ok = false;
    }

    document.body.removeChild(area);

    return ok;
  }

  function copy(button, text) {
    var failure = "Copy failed. Select the text and press Ctrl+C or Cmd+C.";

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () {
          report(button, true, "Copied");
        },
        function () {
          report(button, false, failure);
        }
      );
    } else if (copyWithSelection(text)) {
      report(button, true, "Copied");
    } else {
      report(button, false, failure);
    }
  }

  /* Downloads fetch the real file from the repository, so a blocked or
     missing file is a visible failure beside the button. */
  function download(button, url, name) {
    var served = location.protocol === "http:" || location.protocol === "https:";

    if (!served) {
      report(
        button,
        false,
        "Download failed: open this page through a local web server to download files."
      );

      return;
    }

    fetch(url)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }

        return response.blob();
      })
      .then(function (blob) {
        var objectUrl = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = objectUrl;
        link.download = name;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(function () {
          URL.revokeObjectURL(objectUrl);
        }, 1000);
        report(button, true, "Download started: " + name);
      })
      .catch(function (error) {
        report(button, false, "Download failed: " + error.message);
      });
  }

  function groupButtons(host, items, labelOf, onPick) {
    items.forEach(function (item, index) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "btn";
      button.textContent = labelOf(item);
      button.addEventListener("click", function () {
        onPick(index);
      });
      host.appendChild(button);
    });
  }

  function stageLists() {
    return document.querySelectorAll("[data-path-list]");
  }

  function activeStageButtons() {
    return stageLists()[state.path].querySelectorAll("[data-stage]");
  }

  function bindStageLists() {
    stageLists().forEach(function (list) {
      list.querySelectorAll("[data-stage]").forEach(function (button, index) {
        button.addEventListener("click", function () {
          go(index);
        });
      });
    });
  }

  function render() {
    var stages = currentPath().stages;
    var stage = currentStage();
    var io = currentIo();
    var pathButtons = $("path-buttons").querySelectorAll("button");
    var ticketButtons = $("ticket-buttons").querySelectorAll("button");
    pathButtons.forEach(function (button, index) {
      button.setAttribute("aria-pressed", String(index === state.path));
    });
    ticketButtons.forEach(function (button, index) {
      button.setAttribute("aria-pressed", String(index === state.ticket));
    });
    stageLists().forEach(function (list, index) {
      list.hidden = index !== state.path;
    });
    activeStageButtons().forEach(function (button, index) {
      if (index === state.stage) {
        button.setAttribute("aria-current", "step");
      } else {
        button.removeAttribute("aria-current");
      }
    });
    $("stage-title").textContent = "Stage " + (state.stage + 1) + ": " + stage.title;
    $("stage-component").textContent = stage.component;
    $("stage-about").textContent = stage.about;
    $("stage-input").textContent = pretty(io.input);
    $("stage-output").textContent = pretty(io.output);
    $("stage-code").textContent = stage.code;
    $("where").textContent = "Stage " + (state.stage + 1) + " of " + stages.length;
    $("prev").disabled = state.stage === 0;
    $("next").disabled = state.stage === stages.length - 1;
    var showsGateway = ["reply", "merge", "record"].indexOf(stage.id) >= 0;
    $("gateway-note").textContent = showsGateway
      ? "The gateway also returns " +
        data.omitted_gateway_fields.join(", ") +
        " fields. No pipeline reads them, so they are left out of this view."
      : "";

    try {
      history.replaceState(
        null,
        "",
        "#walk=" + currentPath().id + "," + currentTicket().id + "," + (state.stage + 1)
      );
    } catch (error) {
      /* A sandboxed frame may refuse; the walk still works. */
    }
  }

  /* Re-render in place so the page keeps its scroll position. */
  function keepScroll(change) {
    var x = window.scrollX;
    var y = window.scrollY;
    change();
    window.scrollTo(x, y);
  }

  function go(index) {
    var last = currentPath().stages.length - 1;
    var next = Math.max(0, Math.min(last, index));
    keepScroll(function () {
      state.stage = next;
      render();
    });
  }

  function pickPath(index) {
    keepScroll(function () {
      state.path = index;
      state.stage = Math.min(state.stage, currentPath().stages.length - 1);
      render();
    });
  }

  function pickTicket(index) {
    keepScroll(function () {
      state.ticket = index;
      render();
    });
  }

  function restoreFromHash() {
    var match = /^#walk=([^,]+),([^,]+),(\d+)$/.exec(location.hash);

    if (!match) {
      return;
    }

    var pathIndex = data.paths.findIndex(function (item) {
      return item.id === match[1];
    });

    var ticketIndex = data.tickets.findIndex(function (item) {
      return item.id === match[2];
    });

    if (pathIndex < 0 || ticketIndex < 0) {
      return;
    }

    state.path = pathIndex;
    state.ticket = ticketIndex;
    state.stage = Math.max(0, Math.min(currentPath().stages.length - 1, Number(match[3]) - 1));
  }

  function setTheme(theme) {
    root.setAttribute("data-theme", theme);
    var button = $("theme");
    button.setAttribute("aria-pressed", String(theme === "dark"));
    button.textContent = theme === "dark" ? "Light mode" : "Dark mode";

    try {
      localStorage.setItem("agents-sdk-theme", theme);
    } catch (error) {
      /* Private windows can refuse storage; the choice just will not persist. */
    }
  }

  function init() {
    var saved = null;

    try {
      saved = localStorage.getItem("agents-sdk-theme");
    } catch (error) {
      saved = null;
    }

    setTheme(saved === "dark" ? "dark" : "light");
    $("theme").addEventListener("click", function () {
      setTheme(root.getAttribute("data-theme") === "dark" ? "light" : "dark");
    });

    groupButtons($("path-buttons"), data.paths, function (p) { return p.title; }, pickPath);
    groupButtons(
      $("ticket-buttons"),
      data.tickets,
      function (t) { return t.kind === "recorded" ? t.id : t.id + " (no recorded answer)"; },
      pickTicket
    );
    restoreFromHash();
    bindStageLists();
    render();

    $("prev").addEventListener("click", function () { go(state.stage - 1); });
    $("next").addEventListener("click", function () { go(state.stage + 1); });

    document.addEventListener("keydown", function (event) {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
        return;
      }

      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
        return;
      }

      if (event.target.closest && event.target.closest("input, textarea, select")) {
        return;
      }

      event.preventDefault();
      go(state.stage + (event.key === "ArrowRight" ? 1 : -1));
    });

    document.querySelectorAll("[data-copy-target]").forEach(function (button) {
      button.addEventListener("click", function () {
        var target = button.getAttribute("data-copy-target");
        var io = currentIo();
        var text = target === "code" ? currentStage().code : pretty(io[target]);
        copy(button, text);
      });
    });
    document.querySelectorAll("[data-copy-cmd]").forEach(function (button) {
      button.addEventListener("click", function () {
        copy(button, button.closest("[data-cmd]").querySelector("pre").textContent);
      });
    });

    $("download-yaml").addEventListener("click", function (event) {
      var file = currentPath().pipeline;
      download(event.currentTarget, "../" + file, file.split("/").pop());
    });
    $("download-fixture").addEventListener("click", function (event) {
      var file = currentStage().fixtures.output;
      download(event.currentTarget, "../" + file, file.split("/").pop());
    });
  }

  init();
})();
