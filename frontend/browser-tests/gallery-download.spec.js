const {test,expect}=require('@playwright/test');
test('gallery opens a full image and downloads the actual file',async({page})=>{
 await page.goto('/index.html');
 await page.evaluate(()=>{
  document.getElementById('loginSection').style.display='none';
  document.getElementById('dashboardSection').style.display='grid';
  document.getElementById('ownerManagementTab').style.display='block';
  renderBusinessGallery(['/images/barbershop-hero.png']);
 });
 await page.getByRole('button',{name:'Ver y descargar',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Vista ampliada de la foto'});
 await expect(dialog).toBeVisible();
 const download=page.waitForEvent('download');
 await dialog.getByRole('link',{name:'Descargar foto'}).click();
 expect((await download).suggestedFilename()).toBe('barbershop-hero.png');
 await dialog.getByRole('button',{name:'Cerrar',exact:true}).click();
 await expect(dialog).toHaveCount(0);
});
