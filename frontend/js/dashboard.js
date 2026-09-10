// PramaanCheck - Dashboard Overview Controller

document.addEventListener('DOMContentLoaded', async () => {
  // Check user authentication
  const currentUser = await getCurrentUser();
  if (!currentUser) {
    window.location.href = '/login';
    return;
  }

  // Set navbar user details
  document.getElementById('user-name').textContent = currentUser.name || currentUser.username;
  const roleElem = document.getElementById('user-role');
  roleElem.textContent = currentUser.role;
  roleElem.className = `user-role-tag role-${currentUser.role}`;

  // Load metrics, watchlist & table data
  await loadDashboardStats();
  await loadRiskWatchlist();
  await loadRecentScans();
});

async function loadRiskWatchlist() {
  const tbody = document.getElementById('watchlist-tbody');
  if (!tbody) return;

  try {
    const response = await fetch('/api/dashboard/watchlist', { credentials: 'same-origin' });
    if (!response.ok) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#f87171;">Failed to load risk prioritization engine</td></tr>';
      return;
    }

    const items = await response.json();
    if (!items || items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding: 25px;">No high-risk entities identified yet.</td></tr>';
      return;
    }

    tbody.innerHTML = '';
    items.forEach(item => {
      const tr = document.createElement('tr');

      let riskBg = 'rgba(239, 68, 68, 0.15)';
      let riskColor = '#f87171';
      let riskBorder = '1px solid rgba(239, 68, 68, 0.4)';

      if (item.risk_level === 'HIGH RISK') {
        riskBg = 'rgba(249, 115, 22, 0.15)'; riskColor = '#fb923c'; riskBorder = '1px solid rgba(249, 115, 22, 0.4)';
      } else if (item.risk_level === 'ELEVATED') {
        riskBg = 'rgba(234, 179, 8, 0.15)'; riskColor = '#facc15'; riskBorder = '1px solid rgba(234, 179, 8, 0.4)';
      } else if (item.risk_level === 'LOW') {
        riskBg = 'rgba(34, 197, 94, 0.15)'; riskColor = '#4ade80'; riskBorder = '1px solid rgba(34, 197, 94, 0.4)';
      }

      tr.innerHTML = `
        <td>
          <div style="font-weight: 600; color: #ffffff;">${item.entity_name}</div>
          <div style="font-size: 11px; color: var(--muted);">${item.category}</div>
        </td>
        <td style="font-family: var(--font-mono); font-weight: 600;">
          <span style="color: #ffffff;">${item.total_audits} Audits</span> /
          <span style="color: #f87171;">${item.violations_count} Viols</span>
        </td>
        <td style="font-family: var(--font-mono); font-weight: 600; color: ${item.compliance_rate < 50 ? '#f87171' : '#4ade80'};">
          ${item.compliance_rate}%
        </td>
        <td style="font-size: 12px; color: #e2e8f0; max-width: 220px; white-space: normal;">
          <i class="fa-solid fa-flag" style="color: #f87171; font-size: 10px; margin-right: 4px;"></i>${item.primary_violation}
        </td>
        <td>
          <span style="font-size: 11px; font-weight: 700; background: ${riskBg}; color: ${riskColor}; border: ${riskBorder}; padding: 3px 8px; border-radius: 4px; display: inline-block;">
            ${item.risk_level}
          </span>
        </td>
        <td style="font-size: 12px; color: #94a3b8; font-style: italic;">${item.recommended_action}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Error loading risk watchlist:', err);
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#f87171;">Error loading risk prioritization engine</td></tr>';
  }
}

async function loadDashboardStats() {
  try {
    const response = await fetch('/api/dashboard/stats', { credentials: 'same-origin' });
    if (!response.ok) return;

    const stats = await response.json();
    document.getElementById('stat-total-scans').textContent = stats.total_scans || 0;
    document.getElementById('stat-compliance-rate').textContent = `${stats.compliance_rate || 0}%`;
    document.getElementById('stat-violations').textContent = stats.violations_found || 0;
  } catch (err) {
    console.error('Error loading dashboard stats:', err);
  }
}

async function loadRecentScans() {
  const tbody = document.getElementById('recent-scans-tbody');
  if (!tbody) return;

  try {
    const response = await fetch('/api/scans/recent', { credentials: 'same-origin' });
    if (!response.ok) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--status-fail-text);">Failed to load recent scans</td></tr>';
      return;
    }

    const scans = await response.json();
    if (scans.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding: 30px;">No inspection scans found yet. Click "+ New Label Scan" to perform your first scan.</td></tr>';
      return;
    }

    tbody.innerHTML = '';
    scans.forEach(scan => {
      const tr = document.createElement('tr');

      let badgeClass = 'badge-pass';
      let icon = '✓';
      if (scan.overall_status === 'NON_COMPLIANT') {
        badgeClass = 'badge-fail';
        icon = '✕';
      } else if (scan.overall_status === 'WARNING') {
        badgeClass = 'badge-warn';
        icon = '⚠';
      }
      
      const noteHtml = scan.note ? `<span style="font-size: 12px; font-style: italic; color: #a1a1aa;">${scan.note}</span>` : `<span style="color: rgba(255,255,255,0.1);">-</span>`;

      tr.innerHTML = `
        <td style="font-family: var(--font-mono); font-weight: 600;">#${scan.id}</td>
        <td>
          <div style="font-weight: 500; color: var(--text-primary);">${scan.image_name}</div>
        </td>
        <td>${noteHtml}</td>
        <td>
          <span class="badge ${badgeClass}">${icon} ${scan.overall_status}</span>
        </td>
        <td style="font-family: var(--font-mono); font-weight: 600; color: var(--accent-cyan);">
          ${scan.compliance_score}%
        </td>
        <td>
          <span class="user-role-tag role-${scan.user_role}">${scan.user_role}</span>
        </td>
        <td style="font-size: 12px; color: var(--text-muted);">
          ${scan.created_at || 'Just now'}
        </td>
      `;

      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Error loading recent scans:', err);
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--status-fail-text);">Error loading scan history</td></tr>';
  }
}
