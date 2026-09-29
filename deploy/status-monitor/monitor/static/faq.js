for(const button of document.querySelectorAll("[data-copy-target]")){
  button.addEventListener("click",async()=>{
    const target=document.getElementById(button.dataset.copyTarget);
    const feedback=button.closest(".troubleshooting-body").querySelector(".copy-feedback");
    try{
      await navigator.clipboard.writeText(target.textContent);
      feedback.textContent="地址已复制。";
    }catch{
      const range=document.createRange();range.selectNodeContents(target);
      const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
      feedback.textContent="浏览器未允许自动复制，请复制已选中的地址。";
    }
  });
}
