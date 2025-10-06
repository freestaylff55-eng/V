const apiBase = ''; // same origin

document.getElementById('saveTokenBtn').addEventListener('click', async () => {
  const token = document.getElementById('token').value.trim();
  const label = document.getElementById('label').value.trim() || 'default';
  const resultEl = document.getElementById('saveResult');
  resultEl.innerText = 'جاري الحفظ...';

  try {
    const r = await fetch(apiBase + '/api/save-token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, label })
    });
    const j = await r.json();
    if (j.ok) {
      resultEl.innerText = 'تم الحفظ. يمكنك الآن التعديل.';
      document.getElementById('tokenId').innerText = j.id;
      document.getElementById('step1').classList.add('hidden');
      document.getElementById('dashboard').classList.remove('hidden');
    } else {
      resultEl.innerText = 'خطأ: ' + (j.error || JSON.stringify(j));
    }
  } catch (e) {
    resultEl.innerText = 'خطأ في الاتصال';
    console.error(e);
  }
});

document.getElementById('updateBioBtn').addEventListener('click', async () => {
  const id = Number(document.getElementById('tokenId').innerText);
  const newBio = document.getElementById('newBio').value;
  const resEl = document.getElementById('updateResult');
  resEl.innerText = 'جاري التحديث...';
  try {
    const r = await fetch(apiBase + '/api/update-bio', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, newBio })
    });
    const j = await r.json();
    if (j.ok) {
      resEl.innerText = 'تم التحديث بنجاح.';
      document.getElementById('displayBio').innerText = newBio;
    } else {
      resEl.innerText = 'فشل: ' + (j.error || JSON.stringify(j));
    }
  } catch (e) {
    resEl.innerText = 'خطأ في الاتصال';
    console.error(e);
  }
});

document.getElementById('deleteTokenBtn').addEventListener('click', async () => {
  const id = Number(document.getElementById('tokenId').innerText);
  if (!confirm('هل تريد حذف هذا التوكن من الخادم؟')) return;
  try {
    const r = await fetch(apiBase + '/api/delete-token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id })
    });
    const j = await r.json();
    if (j.ok) {
      alert('تم الحذف');
      location.reload();
    } else alert('فشل الحذف');
  } catch (e) {
    alert('خطأ');
  }
});
