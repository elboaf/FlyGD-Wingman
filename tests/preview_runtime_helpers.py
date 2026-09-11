"""Host lifecycle facts for bridge doubles; no runtime arbitration here.

Tests still use PreviewRuntime's real executor. Each host's start/stop recorders
call the acknowledgments below; families have no native resources in this seam.
"""

from threading import Event

from wingman.preview.runtime import FamilyDemand, HostAck


class HostLifecycle:
    def set_lifecycle_callback(self, callback):
        self._lifecycle_callback = callback
        self._pump_epoch = 0
        self._eve_epoch = 0
        self._companion_epoch = 0
        self._family_demand = FamilyDemand(0, bool(self.is_running), False)
        self._admission_closed = False
        self.started_event = Event()
        self.stopped_event = Event()

    @property
    def runtime_enabled(self):
        if hasattr(self, "_runtime_enabled_override"):
            return self._runtime_enabled_override and not getattr(
                self, "_admission_closed", False
            )
        demand = getattr(self, "_family_demand", None)
        return (
            self.is_running
            and not getattr(self, "_admission_closed", False)
            and (demand is None or demand.eve)
        )

    @runtime_enabled.setter
    def runtime_enabled(self, enabled):
        # Some policy-only tests explicitly inject authorization without a pump.
        self._runtime_enabled_override = enabled

    def set_families(self, demand):
        if self._admission_closed or demand.revision < self._family_demand.revision:
            return False
        previous = self._family_demand
        self._family_demand = demand
        if demand.eve != previous.eve:
            self._eve_epoch += 1
            if self.is_running:
                self._emit("eve-active" if demand.eve else "eve-stopped")
        if demand.companions != previous.companions:
            self._companion_epoch += 1
            if self.is_running:
                self._emit(
                    "companions-active" if demand.companions else "companions-stopped"
                )
        return True

    def _admission_epochs(self):
        return self._pump_epoch, self._eve_epoch, self._companion_epoch

    def _emit(self, outcome):
        self._lifecycle_callback(
            HostAck(self._pump_epoch, self._eve_epoch, self._companion_epoch, outcome)
        )

    def ack_started(self):
        self._pump_epoch += 1
        self._emit("pump-started")
        if self._family_demand.eve:
            self._eve_epoch = max(1, self._eve_epoch)
            self._emit("eve-active")
        if self._family_demand.companions:
            self._emit("companions-active")
        self.started_event.set()

    def ack_stopped(self):
        self._emit("pump-stopped")
        self.stopped_event.set()
        return True

    def close_admission(self):
        self._admission_closed = True
