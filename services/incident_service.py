from collections import defaultdict
import re
from datetime import datetime


class IncidentService:
    def __init__(self, incident_repo, request_repo=None, announcement_service=None, sms_service=None, config=None, session=None):
        self.incident_repo = incident_repo
        self.request_repo = request_repo
        self.announcement_service = announcement_service
        self.sms_service = sms_service
        self.config = config
        self.session = session or {}

    @staticmethod
    def consolidate_by_pincode(incidents: list[dict]) -> list[dict]:
        if not incidents:
            return []
        pincode_groups = defaultdict(list)
        for inc in incidents:
            pincode = inc.get('pincode', 'unknown')
            pincode_groups[pincode].append(inc)
        consolidated = []
        for _, group in pincode_groups.items():
            if len(group) == 1:
                inc = group[0]
                inc['report_count'] = 1
                consolidated.append(inc)
            else:
                main_incident = group[0].copy()
                descriptions = [g.get('description', '') for g in group if g.get('description')]
                if descriptions:
                    main_incident['description'] = IncidentService._unify_description(descriptions)
                main_incident['report_count'] = len(group)
                main_incident['severity'] = max([g.get('severity', 'low') for g in group], key=lambda x: {'low':1,'medium':2,'high':3}.get(x,1))
                timestamps = [g.get('timestamp') for g in group if g.get('timestamp')]
                if timestamps:
                    main_incident['timestamp'] = max(timestamps)
                consolidated.append(main_incident)
        consolidated.sort(key=lambda x: x.get('timestamp',''), reverse=True)
        return consolidated

    @staticmethod
    def _unify_description(descriptions: list[str]) -> str:
        if not descriptions:
            return "Multiple reports of incident in this area"
        cleaned = []
        for d in descriptions:
            if d and d.strip():
                cleaned.append(re.sub(r'\s+', ' ', d.strip()))
        if not cleaned:
            return "Multiple reports of incident in this area"
        if len(cleaned) == 1:
            return cleaned[0]
        all_words = []
        for d in cleaned:
            all_words.extend(re.findall(r'\b\w+\b', d.lower()))
        freq = {}
        for w in all_words:
            if len(w) > 3:
                freq[w] = freq.get(w, 0) + 1
        common = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:5]
        if common:
            key_terms = [w for w, c in common if c > 1]
            base = f"Multiple reports of incident involving: {', '.join(key_terms)}. " if key_terms else "Multiple reports of incident in this area. "
        else:
            base = "Multiple reports of incident in this area. "
        if len(cleaned) <= 3:
            base += "Reports include: " + "; ".join(cleaned[:3])
        else:
            base += f"Reports include: {cleaned[0]} and {len(cleaned)-1} other reports"
        return base

    def report_incident(self, user_id: str, payload: dict) -> int:
        data = {
            "user_id": user_id,
            "location": payload.get("location"),
            "address": payload.get("address") or None,
            "city": payload.get("city") or None,
            "state": payload.get("state") or None,
            "cause": payload.get("cause") or None,
            "pincode": payload.get("pincode"),
            "description": payload.get("description"),
        }
        return self.incident_repo.insert_incident(data)

    def forward_incident(self, admin_id: str, incident_id: int):
        inc = self.incident_repo.get_incident(incident_id)
        if not inc:
            raise ValueError("Incident not found")
        if inc.get('status') == 'forwarded':
            return {"already": True}
        self.incident_repo.update_incident_forwarded(incident_id, datetime.now().isoformat())
        if self.request_repo:
            self.request_repo.insert_request({"admin_id": admin_id, "incident_id": incident_id, "status": "pending"})
        if self.announcement_service:
            self._create_disaster_announcement(admin_id, inc)
        if self.sms_service and self.config and getattr(self.config, 'is_sms_configured') and self.config.is_sms_configured():
            try:
                nearby = self.sms_service.get_nearby_users(inc.get('pincode'), inc.get('location'), radius_km=5)
                self.sms_service.send_bulk_sms(nearby, f"Emergency alert near {inc.get('location')} - Severity {inc.get('severity','medium')}. Stay safe.")
            except Exception:
                pass
        return {"forwarded": True}

    def _create_disaster_announcement(self, admin_id: str, inc: dict):
        if not self.announcement_service:
            return
        title = f"🚨 DISASTER WARNING - {inc.get('location','Unknown Location')}"
        pin = inc.get('pincode')
        if pin:
            title += f" (Pincode: {pin})"
        severity = inc.get('severity','medium')
        desc = (
            f"🚨 EMERGENCY ALERT - VERIFIED INCIDENT 🚨\n\n"
            f"Location: {inc.get('location')}\n"
            f"Pincode: {pin or 'Not specified'}\n"
            f"Severity: {severity.upper()}\n"
            f"Status: VERIFIED & FORWARDED TO GOVERNMENT\n\n"
            f"Details: {inc.get('description','No description available')}\n\n"
            f"⚠️ IMPORTANT SAFETY INSTRUCTIONS:\n"
            f"• Stay indoors and avoid the affected area\n"
            f"• Follow instructions from local authorities\n"
            f"• Keep emergency supplies ready\n"
            f"• Monitor official updates\n\n"
            f"This incident has been verified by our admin team and forwarded to government authorities for immediate action.\n\n"
            f"Stay safe and follow official instructions.\n"
            f"- ResQchain Emergency Management System"
        ).strip()
        payload = {
            'admin_id': admin_id,
            'title': title,
            'description': desc,
            'severity': severity,
            'is_weather_alert': False
        }
        self.announcement_service.ann_repo.create(payload)


