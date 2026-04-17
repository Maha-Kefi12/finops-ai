/**
 * Download utilities for client-side file downloads
 */

/**
 * Download a blob as a file with the given filename
 * @param blob - The data blob to download
 * @param filename - The filename for the downloaded file
 */
export const downloadBlob = (blob, filename) => {
    const url = window.URL.createObjectURL(new Blob([blob]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    link.parentNode.removeChild(link)
    window.URL.revokeObjectURL(url)
}

/**
 * Download a PDF from an API response
 * @param response - The axios response with blob data
 * @param filename - Optional custom filename (extracted from header if not provided)
 */
export const downloadPdf = (response, filename) => {
    // Try to get filename from Content-Disposition header
    let actualFilename = filename
    if (!actualFilename) {
        const contentDisposition = response.headers['content-disposition']
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename[^;=\n]*=(["\']?)([^"'\n]*)\1/i)
            actualFilename = filenameMatch ? filenameMatch[2] : 'download.pdf'
        } else {
            actualFilename = 'export.pdf'
        }
    }
    
    downloadBlob(response.data, actualFilename)
}

export default { downloadBlob, downloadPdf }
